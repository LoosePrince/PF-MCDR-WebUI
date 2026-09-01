import { motion } from 'framer-motion';
import { Maximize, Minimize, X } from 'lucide-react';
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import {
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from '@xyflow/react';
import type { Edge, EdgeProps, Node, NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

export interface RelationPlugin {
  id: string;
  name: string;
  dependencies?: Record<string, string>;
}

export type RelationNodeTone = 'emerald' | 'rose' | 'slate' | 'amber' | 'blue';

interface RelationNode {
  id: string;
  name: string;
  missing: boolean;
}

interface RelationEdge {
  source: string;
  target: string;
}

interface RelationGraph {
  nodes: RelationNode[];
  edges: RelationEdge[];
}

const VIEW_W = 960;
const VIEW_H = 640;

const NODE_STYLES: Record<RelationNodeTone, { fill: string; stroke: string }> = {
  emerald: { fill: '#10b981', stroke: '#047857' },
  rose: { fill: '#f43f5e', stroke: '#be123c' },
  slate: { fill: '#64748b', stroke: '#475569' },
  amber: { fill: '#f59e0b', stroke: '#b45309' },
  blue: { fill: '#3b82f6', stroke: '#1d4ed8' },
};

const MISSING_NODE = { fill: '#ffffff', stroke: '#f59e0b' };
const EDGE_COLOR = '#94a3b8';

function buildGraph(plugins: RelationPlugin[]): RelationGraph {
  const nodeMap = new Map<string, RelationNode>();
  const edgeMap = new Map<string, RelationEdge>();

  for (const plugin of plugins) {
    const pluginId = typeof plugin?.id === 'string' ? plugin.id.trim() : '';
    if (!pluginId) continue;

    // 依赖项可能比插件本体更早出现；本体出现时应覆盖“缺失”占位节点。
    nodeMap.set(pluginId, {
      id: pluginId,
      name: typeof plugin.name === 'string' && plugin.name.trim() ? plugin.name : pluginId,
      missing: false,
    });

    const dependencies = plugin.dependencies;
    if (!dependencies || typeof dependencies !== 'object' || Array.isArray(dependencies)) continue;

    for (const rawDepId of Object.keys(dependencies)) {
      const depId = rawDepId.trim();
      if (!depId || depId === pluginId) continue;
      if (!nodeMap.has(depId)) {
        nodeMap.set(depId, { id: depId, name: depId, missing: true });
      }
      // 在线仓库可能包含重复条目，去重可避免重叠连线和无谓渲染。
      edgeMap.set(`${pluginId}\u0000${depId}`, { source: pluginId, target: depId });
    }
  }

  return { nodes: [...nodeMap.values()], edges: [...edgeMap.values()] };
}

interface LayoutPos {
  x: number;
  y: number;
}

const NODE_DIAMETER = 28;
const NODE_SPACING = 104;
const EDGE_LENGTH = 156;
const LAYOUT_MARGIN = 72;
const MINIMAP_NODE_LIMIT = 160;

/**
 * 使用带位移上限的弹簧布局，并在每轮中执行节点碰撞分离。
 * 坐标不会按固定视口强制缩放，因此大量在线插件也能保持最小间距。
 */
function computeLayout(graph: RelationGraph): Map<string, LayoutPos> {
  const nodes = graph.nodes;
  const n = nodes.length;
  const result = new Map<string, LayoutPos>();
  if (n === 0) return result;
  if (n === 1) {
    result.set(nodes[0].id, { x: VIEW_W / 2, y: VIEW_H / 2 });
    return result;
  }

  const indexById = new Map(nodes.map((node, index) => [node.id, index]));
  const links: Array<[number, number]> = [];
  for (const edge of graph.edges) {
    const source = indexById.get(edge.source);
    const target = indexById.get(edge.target);
    if (source !== undefined && target !== undefined && source !== target) {
      links.push([source, target]);
    }
  }

  // 以不重叠的网格作为确定性初始位置，避免 Math.random 导致布局抖动。
  const columns = Math.max(1, Math.ceil(Math.sqrt((n * VIEW_W) / VIEW_H)));
  const rows = Math.ceil(n / columns);
  const layoutWidth = Math.max(VIEW_W, (columns - 1) * NODE_SPACING + LAYOUT_MARGIN * 2);
  const layoutHeight = Math.max(VIEW_H, (rows - 1) * NODE_SPACING + LAYOUT_MARGIN * 2);
  const startX = (layoutWidth - (columns - 1) * NODE_SPACING) / 2;
  const startY = (layoutHeight - (rows - 1) * NODE_SPACING) / 2;
  const pos = nodes.map((_, index) => ({
    x: startX + (index % columns) * NODE_SPACING,
    y: startY + Math.floor(index / columns) * NODE_SPACING,
  }));

  // 节点仅与相邻网格单元比较，在线插件数量较多时仍可保持线性级碰撞开销。
  const addCollisionForces = (dx: Float64Array, dy: Float64Array) => {
    const cells = new Map<string, number[]>();
    for (let i = 0; i < n; i++) {
      const cellX = Math.floor(pos[i].x / NODE_SPACING);
      const cellY = Math.floor(pos[i].y / NODE_SPACING);
      const key = `${cellX},${cellY}`;
      const entries = cells.get(key);
      if (entries) entries.push(i);
      else cells.set(key, [i]);
    }

    for (let i = 0; i < n; i++) {
      const cellX = Math.floor(pos[i].x / NODE_SPACING);
      const cellY = Math.floor(pos[i].y / NODE_SPACING);
      for (let offsetX = -1; offsetX <= 1; offsetX++) {
        for (let offsetY = -1; offsetY <= 1; offsetY++) {
          const nearby = cells.get(`${cellX + offsetX},${cellY + offsetY}`);
          if (!nearby) continue;
          for (const j of nearby) {
            if (j <= i) continue;
            let deltaX = pos[j].x - pos[i].x;
            let deltaY = pos[j].y - pos[i].y;
            let distance = Math.hypot(deltaX, deltaY);
            if (distance >= NODE_SPACING) continue;
            if (distance < 0.001) {
              // 确定性方向，避免重合节点产生除零或 NaN。
              const angle = ((i + 1) * 2.399963229728653) % (Math.PI * 2);
              deltaX = Math.cos(angle);
              deltaY = Math.sin(angle);
              distance = 1;
            }
            const force = (NODE_SPACING - distance) * 0.62;
            const forceX = (deltaX / distance) * force;
            const forceY = (deltaY / distance) * force;
            dx[i] -= forceX;
            dy[i] -= forceY;
            dx[j] += forceX;
            dy[j] += forceY;
          }
        }
      }
    }
  };

  const iterations = Math.min(220, Math.max(100, 80 + Math.ceil(Math.sqrt(n)) * 4));
  for (let iteration = 0; iteration < iterations; iteration++) {
    const dx = new Float64Array(n);
    const dy = new Float64Array(n);

    // 依赖关系像弹簧一样拉近节点，长边受力更大，短边则适当分开。
    for (const [source, target] of links) {
      const deltaX = pos[target].x - pos[source].x;
      const deltaY = pos[target].y - pos[source].y;
      const distance = Math.max(Math.hypot(deltaX, deltaY), 0.001);
      const force = (distance - EDGE_LENGTH) * 0.035;
      const forceX = (deltaX / distance) * force;
      const forceY = (deltaY / distance) * force;
      dx[source] += forceX;
      dy[source] += forceY;
      dx[target] -= forceX;
      dy[target] -= forceY;
    }

    addCollisionForces(dx, dy);

    const maxStep = 16 - (iteration / iterations) * 12;
    for (let i = 0; i < n; i++) {
      // 轻微中心力防止关联分组无限漂移。
      dx[i] += (layoutWidth / 2 - pos[i].x) * 0.0015;
      dy[i] += (layoutHeight / 2 - pos[i].y) * 0.0015;
      const length = Math.hypot(dx[i], dy[i]);
      const scale = length > maxStep ? maxStep / length : 1;
      const nextX = pos[i].x + dx[i] * scale;
      const nextY = pos[i].y + dy[i] * scale;
      // 最后一层有限值保护，保证 React Flow 永远不会收到 Infinity/NaN。
      pos[i].x = Number.isFinite(nextX)
        ? Math.min(layoutWidth - LAYOUT_MARGIN, Math.max(LAYOUT_MARGIN, nextX))
        : layoutWidth / 2;
      pos[i].y = Number.isFinite(nextY)
        ? Math.min(layoutHeight - LAYOUT_MARGIN, Math.max(LAYOUT_MARGIN, nextY))
        : layoutHeight / 2;
    }
  }

  // 最后单独进行碰撞松弛，确保弹簧布局结束后节点仍保有最小间距。
  for (let pass = 0; pass < 24; pass++) {
    const dx = new Float64Array(n);
    const dy = new Float64Array(n);
    addCollisionForces(dx, dy);
    let moved = false;
    for (let i = 0; i < n; i++) {
      if (Math.abs(dx[i]) + Math.abs(dy[i]) < 0.01) continue;
      moved = true;
      pos[i].x = Math.min(layoutWidth - LAYOUT_MARGIN, Math.max(LAYOUT_MARGIN, pos[i].x + dx[i] * 0.5));
      pos[i].y = Math.min(layoutHeight - LAYOUT_MARGIN, Math.max(LAYOUT_MARGIN, pos[i].y + dy[i] * 0.5));
    }
    if (!moved) break;
  }

  nodes.forEach((node, index) => {
    result.set(node.id, { x: pos[index].x, y: pos[index].y });
  });
  return result;
}

const truncateLabel = (s: string, max = 12) =>
  s.length > max ? `${s.slice(0, max - 1)}…` : s;

// ---------- React Flow node / edge types ----------

// 使用 type 别名以获得隐式索引签名，满足 Node<Data> 的 Record<string, unknown> 约束
type RelationFlowNodeData = {
  name: string;
  missing: boolean;
  tone: RelationNodeTone;
  focused: boolean;
  dimmed: boolean;
  [key: string]: unknown;
};

type RelationFlowNode = Node<RelationFlowNodeData, 'relation'>;
type RelationFlowEdge = Edge;

const getMiniMapNodeColor = (node: Node) => {
  const data = (node as RelationFlowNode).data;
  return data.missing ? '#f59e0b' : NODE_STYLES[data.tone].fill;
};

const getMiniMapNodeStrokeColor = (node: Node) => {
  const data = (node as RelationFlowNode).data;
  return data.missing ? '#f59e0b' : NODE_STYLES[data.tone].stroke;
};

const RelationFlowNodeComponent = memo(function RelationFlowNodeComponent({
  data,
}: NodeProps<RelationFlowNode>) {
  const { name, missing, tone, focused, dimmed } = data;
  const style = missing ? MISSING_NODE : NODE_STYLES[tone];
  return (
    <div
      className="relative select-none"
      title={name}
      style={{ opacity: dimmed ? 0.12 : 1, transition: 'opacity 0.2s', cursor: 'pointer' }}
    >
      <Handle
        type="target"
        position={Position.Top}
        isConnectable={false}
        style={{
          opacity: 0,
          border: 'none',
          background: 'transparent',
          left: '50%',
          top: '50%',
          transform: 'translate(-50%, -50%)',
          pointerEvents: 'none',
        }}
      />
      <div
        style={{
          width: NODE_DIAMETER,
          height: NODE_DIAMETER,
          borderRadius: '50%',
          background: style.fill,
          border: `${focused ? 3 : 2}px solid ${style.stroke}`,
          borderStyle: missing ? 'dashed' : 'solid',
          boxShadow: focused ? `0 0 0 5px ${style.fill}33` : 'none',
          transition: 'border-width 0.15s ease, box-shadow 0.15s ease',
        }}
      />
      <span
        className={`pointer-events-none absolute left-1/2 top-full mt-1 whitespace-nowrap text-[10.5px] font-semibold ${
          missing
            ? 'text-amber-600 dark:text-amber-400'
            : 'text-slate-600 dark:text-slate-300'
        }`}
        style={{ transform: 'translateX(-50%)' }}
      >
        {truncateLabel(name)}
      </span>
      <Handle
        type="source"
        position={Position.Bottom}
        isConnectable={false}
        style={{
          opacity: 0,
          border: 'none',
          background: 'transparent',
          left: '50%',
          top: '50%',
          transform: 'translate(-50%, -50%)',
          pointerEvents: 'none',
        }}
      />
    </div>
  );
});

const NODE_TYPES = { relation: RelationFlowNodeComponent };

/**
 * Handle 位于节点中心，React Flow 会只为受影响的边计算这些坐标。
 * 此处做一次轻量向量运算，将直线端点移动到圆周，避免每条边额外订阅节点状态。
 */
const FloatingStraightEdge = memo(function FloatingStraightEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  markerEnd,
  style,
}: EdgeProps) {
  const deltaX = targetX - sourceX;
  const deltaY = targetY - sourceY;
  const distance = Math.hypot(deltaX, deltaY);
  if (!Number.isFinite(distance) || distance < 0.001) return null;

  const radius = NODE_DIAMETER / 2;
  const unitX = deltaX / distance;
  const unitY = deltaY / distance;
  const edgeSourceX = sourceX + unitX * radius;
  const edgeSourceY = sourceY + unitY * radius;
  const edgeTargetX = targetX - unitX * radius;
  const edgeTargetY = targetY - unitY * radius;
  const coordinates = [edgeSourceX, edgeSourceY, edgeTargetX, edgeTargetY];
  if (!coordinates.every(Number.isFinite)) return null;

  return (
    <BaseEdge
      id={id}
      path={`M ${edgeSourceX} ${edgeSourceY} L ${edgeTargetX} ${edgeTargetY}`}
      markerEnd={markerEnd}
      style={style}
      interactionWidth={0}
    />
  );
});

const EDGE_TYPES = { floatingStraight: FloatingStraightEdge };

// ---------- Inner flow (needs ReactFlowProvider) ----------

const RelationFlowInner: React.FC<{
  graph: RelationGraph;
  layout: Map<string, LayoutPos>;
  nodeTone?: (id: string) => RelationNodeTone;
}> = ({ graph, layout, nodeTone }) => {
  const { fitView, setCenter, setEdges, setNodes } = useReactFlow();
  const [focusId, setFocusId] = useState<string | null>(null);

  // 1 跳关联集合：聚焦节点 + 其直接依赖 / 被依赖节点
  const related = useMemo(() => {
    if (!focusId) return null;
    const set = new Set<string>([focusId]);
    for (const e of graph.edges) {
      if (e.source === focusId) set.add(e.target);
      if (e.target === focusId) set.add(e.source);
    }
    return set;
  }, [focusId, graph.edges]);

  // 读取最新的 nodeTone 而无需重建 memo（其身份每次渲染都会变化）
  const nodeToneRef = useRef(nodeTone);
  nodeToneRef.current = nodeTone;

  const initialNodes = useMemo<RelationFlowNode[]>(
    () =>
      graph.nodes.map((node) => {
        const p = layout.get(node.id);
        const tone = node.missing
          ? 'amber'
          : nodeToneRef.current
            ? nodeToneRef.current(node.id)
            : 'blue';
        return {
          id: node.id,
          type: 'relation',
          position: p ? { x: p.x, y: p.y } : { x: VIEW_W / 2, y: VIEW_H / 2 },
          data: {
            name: node.name,
            missing: node.missing,
            tone,
            focused: false,
            dimmed: false,
          },
        };
      }),
    [graph, layout]
  );

  const initialEdges = useMemo<RelationFlowEdge[]>(
    () =>
      graph.edges.map((e, i) => ({
        id: `rel-edge-${i}`,
        source: e.source,
        target: e.target,
        type: 'floatingStraight',
        markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLOR, width: 16, height: 16 },
        style: { stroke: EDGE_COLOR, strokeWidth: 1.4, opacity: 0.9 },
      })),
    [graph]
  );

  // React Flow 内部维护拖拽位置，避免拖拽每一帧触发本组件重新渲染。
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
    setFocusId(null);
    const frame = window.requestAnimationFrame(() => {
      void fitView({ padding: 0.18, maxZoom: 1.1 });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [fitView, initialEdges, initialNodes, setEdges, setNodes]);

  // 聚焦变化是低频操作，此时才批量更新节点与边的淡化样式。
  useEffect(() => {
    setNodes((nodes) =>
      nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          focused: focusId === node.id,
          dimmed: related ? !related.has(node.id) : false,
        },
      }))
    );
    setEdges(
      initialEdges.map((edge) => ({
        ...edge,
        style: {
          ...edge.style,
          opacity: related
            ? related.has(edge.source) && related.has(edge.target)
              ? 0.9
              : 0.08
            : 0.9,
        },
      }))
    );
  }, [focusId, initialEdges, related, setEdges, setNodes]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: RelationFlowNode) => {
      if (focusId === node.id) {
        setFocusId(null);
        return;
      }
      setFocusId(node.id);
      // 将选中节点移到视口中心并放大
      setCenter(node.position.x, node.position.y, { zoom: 1.2, duration: 350 });
    },
    [focusId, setCenter]
  );

  const handlePaneClick = useCallback(() => setFocusId(null), []);
  const showMiniMap = graph.nodes.length <= MINIMAP_NODE_LIMIT;

  return (
    <ReactFlow
      defaultNodes={initialNodes}
      defaultEdges={initialEdges}
      nodeTypes={NODE_TYPES}
      edgeTypes={EDGE_TYPES}
      onNodeClick={handleNodeClick}
      onPaneClick={handlePaneClick}
      fitView
      fitViewOptions={{ padding: 0.18, maxZoom: 1.1 }}
      minZoom={0.1}
      maxZoom={3}
      onlyRenderVisibleElements
      nodesConnectable={false}
      nodesFocusable={false}
      nodesDraggable
      panOnDrag
      zoomOnScroll
      zoomOnPinch
      deleteKeyCode={null}
      edgesFocusable={false}
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.5} color="var(--xy-dot-color)" />
      <Controls position="bottom-left" showInteractive={false} />
      {showMiniMap && (
        <MiniMap
          pannable
          zoomable
          bgColor="var(--xy-minimap-bg)"
          maskColor="var(--xy-minimap-mask)"
          nodeColor={getMiniMapNodeColor}
          nodeStrokeColor={getMiniMapNodeStrokeColor}
          className="!border !border-slate-200 dark:!border-slate-700"
          style={{ borderRadius: 10, overflow: 'hidden' }}
        />
      )}
    </ReactFlow>
  );
};

// ---------- Modal ----------

export const PluginRelationModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  plugins: RelationPlugin[];
  nodeTone?: (id: string) => RelationNodeTone;
}> = ({ isOpen, onClose, plugins, nodeTone }) => {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const graph = useMemo(() => buildGraph(plugins), [plugins]);
  const layout = useMemo(() => computeLayout(graph), [graph]);

  useEffect(() => {
    const onFullscreenChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  const toggleFullscreen = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      el.requestFullscreen().catch(() => {});
    }
  }, []);

  if (!isOpen) return null;

  return createPortal(
    <div
      className={`fixed inset-0 z-[60] flex items-center justify-center ${isFullscreen ? 'p-0' : 'p-4'}`}
    >
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/60"
      />
      <motion.div
        ref={containerRef}
        initial={{ scale: 0.95, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 20 }}
        onClick={(e) => e.stopPropagation()}
        className={`relative bg-white dark:bg-slate-900 shadow-2xl border border-slate-200 dark:border-slate-800 z-10 flex flex-col transition-[border-radius] duration-200 ${
          isFullscreen ? 'w-full h-full max-w-none rounded-none p-6' : 'w-full max-w-5xl rounded-3xl p-6'
        }`}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-bold text-slate-900 dark:text-white">
            {t('plugins.relation_modal.title')}
          </h3>
          <div className="flex items-center gap-1">
            <button
              onClick={toggleFullscreen}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1"
              aria-label={t(
                isFullscreen
                  ? 'plugins.relation_modal.exit_fullscreen'
                  : 'plugins.relation_modal.fullscreen'
              )}
              title={t(
                isFullscreen
                  ? 'plugins.relation_modal.exit_fullscreen'
                  : 'plugins.relation_modal.fullscreen'
              )}
            >
              {isFullscreen ? <Minimize size={24} /> : <Maximize size={24} />}
            </button>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1"
              aria-label={t('common.close')}
            >
              <X size={24} />
            </button>
          </div>
        </div>

        <div
          className={`bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden relative ${
            isFullscreen ? 'flex-1 min-h-0' : 'h-[65vh] min-h-[420px]'
          }`}
        >
          {graph.nodes.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-400 dark:text-slate-500 text-sm">
              {t('plugins.relation_modal.empty')}
            </div>
          ) : (
            <ReactFlowProvider>
              <RelationFlowInner graph={graph} layout={layout} nodeTone={nodeTone} />
            </ReactFlowProvider>
          )}
        </div>

        <div className="flex items-center justify-between gap-4 mt-3 text-xs text-slate-500 dark:text-slate-400 flex-wrap">
          <span>{t('plugins.relation_modal.hint')}</span>
          <span className="font-semibold whitespace-nowrap">
            {t('plugins.relation_modal.count', {
              nodes: graph.nodes.length,
              edges: graph.edges.length,
            })}
          </span>
        </div>
      </motion.div>
    </div>,
    document.body
  );
};

export default PluginRelationModal;
