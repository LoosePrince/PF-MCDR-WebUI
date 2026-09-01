import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import React from 'react'
import { formatTimeAxis } from '../utils/format'

/** 曲线数据键：cpu/memory 用 system+minecraft，network 用 rx+tx，其余用 value */
export type ChartSeriesKey = 'system' | 'minecraft' | 'rx' | 'tx' | 'value'

export interface ChartPoint {
  t: number
  [key: string]: number | null | undefined
}

export interface ChartSeriesDef {
  key: ChartSeriesKey
  color: string
}

interface StatusChartProps {
  data: ChartPoint[]
  series: ChartSeriesDef[]
  height?: number
  dark: boolean
  yDomain?: [number | string, number | string]
  /** Y 轴紧凑格式化（百分比 / 速度等） */
  yTickFormatter?: (v: number) => string
  /** Tooltip 数值完整格式化 */
  tooltipValueFormatter?: (key: ChartSeriesKey, v: number) => string
  /** 时间轴是否带日期（长范围） */
  xLong?: boolean
}

interface TooltipEntry {
  dataKey?: string | number
  value?: number | string | Array<number | string>
  color?: string
}

const StatusChartTooltip: React.FC<{
  active?: boolean
  label?: number | string
  payload?: TooltipEntry[]
  series: ChartSeriesDef[]
  names: Record<string, string>
  formatter?: (key: ChartSeriesKey, v: number) => string
  xLong?: boolean
}> = ({ active, label, payload, series, names, formatter, xLong = false }) => {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg px-3 py-2 text-xs">
      <div className="font-semibold text-slate-700 dark:text-slate-200 mb-1">
        {formatTimeAxis(Number(label ?? 0), xLong)}
      </div>
      {payload.map((p) => {
        const key = String(p.dataKey ?? '') as ChartSeriesKey
        const def = series.find((s) => s.key === key)
        if (!def) return null
        const value = typeof p.value === 'number' ? p.value : null
        return (
          <div key={key} className="flex items-center gap-2 py-0.5">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: def.color }} />
            <span className="text-slate-500 dark:text-slate-400">{names[key]}</span>
            <span className="ml-auto pl-4 font-semibold text-slate-800 dark:text-slate-100">
              {value !== null && formatter ? formatter(key, value) : '—'}
            </span>
          </div>
        )
      })}
    </div>
  )
}

const StatusChart: React.FC<StatusChartProps & { names: Record<string, string> }> = ({
  data,
  series,
  names,
  height = 220,
  dark,
  yDomain,
  yTickFormatter,
  tooltipValueFormatter,
  xLong = false,
}) => {
  const gridColor = dark ? '#1e293b' : '#e2e8f0'
  const axisColor = dark ? '#94a3b8' : '#64748b'
  const tickStyle = { fill: axisColor, fontSize: 11 }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
        <XAxis
          dataKey="t"
          type="number"
          scale="time"
          domain={['dataMin', 'dataMax']}
          tickFormatter={(v: number) => formatTimeAxis(v, xLong)}
          stroke={axisColor}
          tick={tickStyle}
          tickLine={false}
          axisLine={{ stroke: gridColor }}
          minTickGap={48}
        />
        <YAxis
          stroke={axisColor}
          tick={tickStyle}
          tickLine={false}
          axisLine={false}
          width={46}
          domain={yDomain ?? [0, 'auto']}
          tickFormatter={yTickFormatter}
        />
        <Tooltip
          content={
            <StatusChartTooltip series={series} names={names} formatter={tooltipValueFormatter} xLong={xLong} />
          }
        />
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            stroke={s.color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3 }}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

export default StatusChart