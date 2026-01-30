import React, { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Puzzle,
  Search,
  RotateCw,
  Trash2,
  Settings,
  AlertTriangle,
  Tag,
  ArrowLeft,
  FileText,
  Save as SaveIcon,
  ChevronRight,
  Info,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  Play,
  Square,
  Shield,
  Github,
  Package,
  ArrowUpCircle,
  Download
} from 'lucide-react';
import axios from 'axios';
import { VersionSelectModal } from '../components/VersionSelectModal';

interface PluginDescription {
  [key: string]: string;
}

interface PluginMetadata {
  id: string;
  name: string;
  description: string | PluginDescription;
  author: string;
  github: string;
  version: string;
  version_latest: string;
  status: 'loaded' | 'disabled' | 'unloaded';
  path: string;
  config_file: boolean;
  repository?: {
    name: string;
    url: string;
    is_official: boolean;
  };
}

interface TaskStatus {
  status: string; // 后端返回的状态: pending|running|completed|failed
  message: string;
  all_messages: string[]; // 后端返回的所有消息
  plugin_id?: string;
}

// 懒加载 CodeMirror 编辑器组件
const CodeMirrorEditor: React.FC<{ value: string; onChange: (value: string) => void; theme: string }> = ({ value, onChange, theme }) => {
  const [CodeMirror, setCodeMirror] = useState<any>(null);
  const [jsonLang, setJsonLang] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      import('@uiw/react-codemirror'),
      import('@codemirror/lang-json')
    ]).then(([codemirrorModule, jsonModule]) => {
      setCodeMirror(() => codemirrorModule.default);
      setJsonLang(() => jsonModule.json);
      setLoading(false);
    });
  }, []);

  if (loading || !CodeMirror || !jsonLang) {
    return (
      <div className="flex items-center justify-center h-[400px]">
        <Loader2 className="animate-spin text-blue-500 w-8 h-8" />
      </div>
    );
  }

  return (
    <CodeMirror
      value={value}
      height="400px"
      extensions={[jsonLang()]}
      theme={theme as any}
      onChange={onChange}
    />
  );
};

const LocalPlugins: React.FC = () => {
  const { t, i18n } = useTranslation();
  const [plugins, setPlugins] = useState<PluginMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<'all' | 'loaded' | 'unloaded' | 'disabled'>('all');

  // Task state
  const [installingTaskId, setInstallingTaskId] = useState<string | null>(null);
  const [taskProgress, setTaskProgress] = useState<TaskStatus | null>(null);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [operatingPluginId, setOperatingPluginId] = useState<string>('');
  const [operationType, setOperationType] = useState<'install' | 'update' | 'uninstall'>('install');
  const taskPollingRef = useRef(false);

  // Notification state
  const [showNotification, setShowNotification] = useState(false);
  const [notificationMsg, setNotificationMsg] = useState('');
  const [notificationType, setNotificationType] = useState<'success' | 'error'>('success');

  // Config modal state
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [selectedPlugin, setSelectedPlugin] = useState<PluginMetadata | null>(null);
  const [configFiles, setConfigFiles] = useState<string[]>([]);
  const [loadingConfigs, setLoadingConfigs] = useState(false);

  // Confirm modal state
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [pendingAction, setPendingAction] = useState<{ type: string; plugin: PluginMetadata } | null>(null);

  // Config editor state
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [configContent, setConfigContent] = useState('');
  const [editorMode, setEditorMode] = useState<'code' | 'form'>('code');
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  const [configData, setConfigData] = useState<any>(null);

  // Version modal state
  const [showVersionModal, setShowVersionModal] = useState(false);
  const [availableVersions, setAvailableVersions] = useState<any[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);

  const fetchPlugins = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const resp = await axios.get('/api/plugins', { signal });
      const pluginList = resp.data.plugins || [];

      // Fetch repository info for each plugin concurrently
      const pluginsWithRepo = await Promise.all(pluginList.map(async (p: PluginMetadata) => {
        try {
          const repoResp = await axios.get(`/api/pim/plugin_repository?plugin_id=${p.id}`, { signal });
          if (repoResp.data.success) {
            return { ...p, repository: repoResp.data.repository };
          }
        } catch (e: any) {
          // 忽略取消的请求错误和repo获取错误
          if (axios.isCancel(e) || e.name === 'AbortError' || e.code === 'ERR_CANCELED') {
            throw e; // 重新抛出取消错误，让外层处理
          }
          // Ignore repo fetch errors
        }
        return p;
      }));

      setPlugins(pluginsWithRepo);
    } catch (error: any) {
      // 忽略取消的请求错误
      if (axios.isCancel(error) || error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
        return;
      }
      console.error('Failed to fetch plugins:', error);
      notify(t('plugins.msg.load_plugins_failed'), 'error');
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    // 创建 AbortController 用于取消请求
    const abortController = new AbortController();
    const signal = abortController.signal;

    fetchPlugins(signal);

    return () => {
      // 取消所有进行中的请求
      abortController.abort();
    };
  }, [fetchPlugins]);

  const notify = (msg: string, type: 'success' | 'error') => {
    setNotificationMsg(msg);
    setNotificationType(type);
    setShowNotification(true);
    setTimeout(() => setShowNotification(false), 3000);
  };

  const pollTaskStatus = useCallback(async (taskId: string) => {
    if (taskPollingRef.current) {
      setTimeout(() => pollTaskStatus(taskId), 1000);
      return;
    }
    taskPollingRef.current = true;
    try {
      const resp = await axios.get(`/api/pim/task_status?task_id=${taskId}`);
      if (resp.data.success && resp.data.task_info) {
        const taskInfo = resp.data.task_info;
        const status: TaskStatus = {
          status: taskInfo.status,
          message: taskInfo.message || '',
          all_messages: taskInfo.all_messages || [],
          plugin_id: taskInfo.plugin_id
        };
        setTaskProgress(status);
        if (status.status === 'completed' || status.status === 'failed') {
          setInstallingTaskId(null);
          fetchPlugins();
          if (status.status === 'completed') {
            notify(t('plugins.msg.operation_success', { pluginId: operatingPluginId }), 'success');
          } else {
            notify(t('plugins.msg.operation_failed_prefix', { pluginId: operatingPluginId, message: status.message }), 'error');
          }
        } else {
          setTimeout(() => pollTaskStatus(taskId), 1000);
        }
      } else {
        // 如果请求失败，继续轮询
        setTimeout(() => pollTaskStatus(taskId), 1000);
      }
    } catch (error) {
      console.error('Failed to poll task status:', error);
      // 发生错误时继续轮询，不要立即停止
      setTimeout(() => pollTaskStatus(taskId), 1000);
    } finally {
      taskPollingRef.current = false;
    }
  }, [fetchPlugins, operatingPluginId, t]);

  useEffect(() => {
    if (installingTaskId) {
      pollTaskStatus(installingTaskId);
    }
  }, [installingTaskId, pollTaskStatus]);

  const handleToggle = async (plugin: PluginMetadata) => {
    if (plugin.id === 'guguwebui') {
      notify(t('plugins.msg.cannot_toggle_webui'), 'error');
      return;
    }

    try {
      // status 'loaded' -> false (unload), others -> true (load)
      const targetStatus = plugin.status !== 'loaded';
      const resp = await axios.post('/api/toggle_plugin', {
        plugin_id: plugin.id,
        status: targetStatus
      });

      if (resp.data.status === 'success') {
        notify(targetStatus ? t('plugins.msg.enable_success') : t('plugins.msg.disable_success'), 'success');
        fetchPlugins();
      } else {
        notify(targetStatus
          ? t('plugins.msg.enable_failed_prefix', { message: resp.data.message })
          : t('plugins.msg.disable_failed_prefix', { message: resp.data.message }),
          'error');
      }
    } catch (error: any) {
      notify(t('plugins.msg.enable_failed'), 'error');
    }
  };

  const handleReload = async (plugin: PluginMetadata) => {
    if (plugin.id === 'guguwebui') {
      notify(t('plugins.msg.cannot_reload_webui'), 'error');
      return;
    }

    try {
      const resp = await axios.post('/api/reload_plugin', {
        plugin_id: plugin.id
      });
      if (resp.data.status === 'success') {
        notify(t('plugins.msg.reload_success'), 'success');
        fetchPlugins();
      } else {
        notify(t('plugins.msg.reload_failed_prefix', { message: resp.data.message }), 'error');
      }
    } catch (error) {
      notify(t('plugins.msg.reload_failed'), 'error');
    }
  };

  const handleUninstall = (plugin: PluginMetadata) => {
    if (plugin.id === 'guguwebui') {
      notify(t('plugins.msg.cannot_uninstall_webui'), 'error');
      return;
    }
    setPendingAction({ type: 'uninstall', plugin });
    setShowConfirmModal(true);
  };

  const confirmUninstall = async (plugin: PluginMetadata) => {
    try {
      const resp = await axios.post('/api/pim/uninstall_plugin', {
        plugin_id: plugin.id
      });
      if (resp.data.success) {
        setInstallingTaskId(resp.data.task_id);
        setOperatingPluginId(plugin.id);
        setOperationType('uninstall');
        setTaskProgress(null);
        setShowTaskModal(true);
      } else {
        notify(t('plugins.msg.uninstall_failed_prefix', { message: resp.data.error }), 'error');
      }
    } catch (error) {
      notify(t('plugins.msg.uninstall_failed'), 'error');
    }
  };

  const handleUpdate = (plugin: PluginMetadata) => {
    if (plugin.id === 'guguwebui') {
      notify(t('plugins.msg.cannot_update_webui'), 'error');
      return;
    }
    setPendingAction({ type: 'update', plugin });
    setShowConfirmModal(true);
  };

  const confirmUpdate = async (plugin: PluginMetadata) => {
    try {
      const resp = await axios.post('/api/pim/update_plugin', {
        plugin_id: plugin.id
      });
      if (resp.data.success) {
        setInstallingTaskId(resp.data.task_id);
        setOperatingPluginId(plugin.id);
        setOperationType('update');
        setTaskProgress(null);
        setShowTaskModal(true);
      } else {
        notify(t('plugins.msg.update_failed_prefix', { message: resp.data.error }), 'error');
      }
    } catch (error) {
      notify(t('plugins.msg.update_failed'), 'error');
    }
  };

  const openConfig = async (plugin: PluginMetadata) => {
    setSelectedPlugin(plugin);
    setLoadingConfigs(true);
    setShowConfigModal(true);
    setEditingFile(null); // Reset editing file
    try {
      const resp = await axios.get(`/api/list_config_files?plugin_id=${plugin.id}`);
      setConfigFiles(resp.data.files || []);
    } catch (error) {
      notify(t('plugins.msg.load_config_files_failed'), 'error');
    } finally {
      setLoadingConfigs(false);
    }
  };

  const handleEditFile = async (file: string, mode: 'code' | 'form' = 'code') => {
    setEditingFile(file);
    setEditorMode(mode);
    setLoadingConfigs(true);
    try {
      if (mode === 'code') {
        const resp = await axios.get(`/api/load_config_file?path=${encodeURIComponent(file)}`);
        const data = resp.data;
        setConfigContent(typeof data === 'string' ? data : JSON.stringify(data, null, 2));
      } else {
        const resp = await axios.get(`/api/load_config?path=${encodeURIComponent(file)}`);
        setConfigData(resp.data);
      }
    } catch (error) {
      notify(t('plugins.msg.load_file_failed'), 'error');
      setEditingFile(null);
    } finally {
      setLoadingConfigs(false);
    }
  };

  const handleSaveFile = async () => {
    if (!editingFile) return;
    setIsSavingConfig(true);
    try {
      let resp;
      if (editorMode === 'code') {
        resp = await axios.post('/api/save_config_file', {
          action: editingFile,
          content: configContent
        });
      } else {
        resp = await axios.post('/api/save_config', {
          file_path: editingFile,
          config_data: configData
        });
      }

      if (resp.data.status === 'success') {
        notify(t('page.mcdr.msg.save_success'), 'success');
        setEditingFile(null);
      } else {
        notify(t('plugins.msg.save_failed_prefix', { message: resp.data.message }), 'error');
      }
    } catch (error: any) {
      notify(t('plugins.msg.save_error'), 'error');
    } finally {
      setIsSavingConfig(false);
    }
  };

  const handleReloadAll = async () => {
    try {
      const resp = await axios.post('/api/reload_all_plugins');
      if (resp.data.status === 'success') {
        notify(t('plugins.msg.reload_success'), 'success');
        fetchPlugins();
      } else {
        notify(t('plugins.msg.reload_failed_prefix', { message: resp.data.message }), 'error');
      }
    } catch (error: any) {
      notify(t('plugins.msg.reload_failed'), 'error');
    }
  };

  const formatDate = (dateString: string | undefined): string => {
    if (!dateString) return '';
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) return '';
      return date.toLocaleDateString(i18n.language === 'zh-CN' ? 'zh-CN' : 'en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch {
      return '';
    }
  };

  const openVersions = async (plugin: PluginMetadata) => {
    setSelectedPlugin(plugin);
    setLoadingVersions(true);
    setShowVersionModal(true);
    try {
      const resp = await axios.get(`/api/pim/plugin_versions_v2?plugin_id=${plugin.id}`);
      if (resp.data.success) {
        // 映射后端字段到前端字段，并格式化日期
        const versions = (resp.data.versions || []).map((v: any) => ({
          ...v,
          date: formatDate(v.release_date),
          downloads: v.download_count || 0
        }));
        setAvailableVersions(versions);
      } else {
        setAvailableVersions([]);
      }
    } catch (error) {
      notify(t('plugins.msg.load_versions_failed'), 'error');
    } finally {
      setLoadingVersions(false);
    }
  };

  const filteredPlugins = plugins.filter(p => {
    const matchesSearch = p.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesTab = activeTab === 'all' || p.status === activeTab;
    return matchesSearch && matchesTab;
  });

  const getLocalizedDescription = (desc: string | PluginDescription) => {
    if (typeof desc === 'string') return desc;

    // Normalize language key (zh-CN -> zh_cn)
    const currentLang = i18n.language.toLowerCase().replace('-', '_');

    // Try current lang, then fallback to zh_cn, then en_us, then first available
    return desc[currentLang] || desc['zh_cn'] || desc['en_us'] || Object.values(desc)[0] || '';
  };

  return (
    <div className="space-y-8 pb-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
            <Puzzle className="text-blue-500" />
            {t('nav.local_plugins')}
          </h1>
          <p className="mt-1 text-slate-600 dark:text-slate-400">
            {t('page.local_plugins.title')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleReloadAll}
            className="flex items-center gap-2 px-4 py-2 bg-blue-50 dark:bg-blue-900/10 text-blue-600 border border-blue-200 dark:border-blue-800/50 rounded-xl hover:bg-blue-100 transition-colors shadow-sm font-semibold text-sm"
          >
            <RotateCw size={18} />
            {t('plugins.refresh_plugins')}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-4 items-center justify-between bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div className="relative w-full md:w-96">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
          <input
            type="text"
            placeholder={t('plugins.search_placeholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-blue-500/50 outline-none transition-all"
          />
        </div>
        <div className="flex gap-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-lg shrink-0">
          {(['all', 'loaded', 'unloaded', 'disabled'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${activeTab === tab
                ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
            >
              {t(`plugins.${tab}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Plugin Grid */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-24">
          <Loader2 className="w-12 h-12 text-blue-500 animate-spin mb-4" />
          <p className="text-slate-500 animate-pulse">{t('plugins.loading_plugins')}</p>
        </div>
      ) : filteredPlugins.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <AnimatePresence>
            {filteredPlugins.map((plugin) => (
              <PluginCard
                key={plugin.id}
                plugin={plugin}
                t={t}
                onToggle={handleToggle}
                onReload={handleReload}
                onUninstall={handleUninstall}
                onUpdate={handleUpdate}
                onConfig={openConfig}
                onVersions={openVersions}
                getLocalizedDescription={getLocalizedDescription}
              />
            ))}
          </AnimatePresence>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-24 bg-white dark:bg-slate-900 rounded-3xl border border-dashed border-slate-200 dark:border-slate-800">
          <Puzzle className="w-16 h-16 text-slate-300 mb-4" />
          <p className="text-slate-500">{t('plugins.no_plugins_found')}</p>
        </div>
      )}

      {/* Confirm Modal */}
      <Modal
        isOpen={showConfirmModal}
        onClose={() => setShowConfirmModal(false)}
        title={t(`plugins.confirm_modal.title_${pendingAction?.type}`)}
      >
        <div className="space-y-6">
          <div className="flex items-start gap-4 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-900/30 rounded-2xl">
            <AlertTriangle className="text-amber-500 shrink-0" size={24} />
            <div className="space-y-1">
              <p className="text-sm font-bold text-amber-900 dark:text-amber-200">
                {t(`plugins.confirm_modal.message_${pendingAction?.type}`, { pluginId: pendingAction?.plugin?.id })}
              </p>
              {pendingAction?.type === 'uninstall' && (
                <p className="text-xs text-amber-700 dark:text-amber-400 opacity-80">
                  {t('plugins.confirm_modal.uninstall_warning')}
                </p>
              )}
            </div>
          </div>
          <div className="flex gap-3 pt-2">
            <button
              onClick={() => setShowConfirmModal(false)}
              className="flex-1 px-6 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl transition-colors font-semibold"
            >
              {t('common.cancel')}
            </button>
            <button
              onClick={() => {
                if (pendingAction?.type === 'uninstall') confirmUninstall(pendingAction.plugin);
                if (pendingAction?.type === 'update') confirmUpdate(pendingAction.plugin);
                setShowConfirmModal(false);
              }}
              className={`flex-1 px-6 py-2.5 text-white rounded-xl transition-all shadow-lg font-bold ${pendingAction?.type === 'uninstall'
                ? 'bg-rose-500 hover:bg-rose-600 shadow-rose-500/20'
                : 'bg-amber-500 hover:bg-amber-600 shadow-amber-500/20'
                }`}
            >
              {t('common.confirm')}
            </button>
          </div>
        </div>
      </Modal>

      {/* Task Progress Modal */}
      <Modal
        isOpen={showTaskModal}
        onClose={() => !installingTaskId && setShowTaskModal(false)}
        title={t(`plugins.install_modal.${operationType}_progress`) + operatingPluginId}
      >
        <div className="space-y-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-slate-600 dark:text-slate-400">
              {taskProgress && (taskProgress.status === 'completed' || taskProgress.status === 'failed') ? t('plugins.install_modal.completed') : t('plugins.install_modal.processing')}
            </span>
            {taskProgress && (taskProgress.status === 'completed' || taskProgress.status === 'failed') && (
              <span className={`text-sm font-bold ${taskProgress.status === 'completed' ? 'text-emerald-500' : 'text-rose-500'}`}>
                {taskProgress.status === 'completed' ? t('common.success') : t('common.failed')}
              </span>
            )}
          </div>

          <div className="bg-slate-950 rounded-2xl p-4 font-mono text-xs text-slate-300 h-64 overflow-y-auto space-y-1 custom-scrollbar">
            {taskProgress && taskProgress.all_messages.length > 0 ? (
              taskProgress.all_messages.map((line, i) => (
                <div key={i} className="break-all whitespace-pre-wrap">{line}</div>
              ))
            ) : (
              <div className="text-slate-500 animate-pulse">{t('plugins.install_modal.waiting_logs')}</div>
            )}
          </div>

          <div className="flex justify-end pt-2">
            <button
              disabled={!!installingTaskId}
              onClick={() => setShowTaskModal(false)}
              className="px-6 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 text-slate-700 dark:text-slate-200 rounded-xl transition-colors font-semibold"
            >
              {t('common.confirm')}
            </button>
          </div>
        </div>
      </Modal>

      {/* Config Modal */}
      <Modal
        isOpen={showConfigModal}
        onClose={() => setShowConfigModal(false)}
        title={t('plugins.config_modal.title') + ' - ' + selectedPlugin?.name}
        fullWidth={!!editingFile}
      >
        <div className="space-y-4">
          {loadingConfigs ? (
            <div className="flex justify-center py-12">
              <Loader2 className="animate-spin text-blue-500 w-10 h-10" />
            </div>
          ) : editingFile ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <button
                  onClick={() => setEditingFile(null)}
                  className="flex items-center gap-2 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
                >
                  <ArrowLeft size={18} />
                  <span>{t('plugins.config_modal.back_to_list')}</span>
                </button>
                <div className="flex gap-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-lg">
                  <button
                    onClick={() => handleEditFile(editingFile, 'code')}
                    className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${editorMode === 'code' ? 'bg-white dark:bg-slate-700 text-blue-600 shadow-sm' : 'text-slate-500'}`}
                  >
                    {t('plugins.config_modal.code_view')}
                  </button>
                  <button
                    onClick={() => handleEditFile(editingFile, 'form')}
                    className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${editorMode === 'form' ? 'bg-white dark:bg-slate-700 text-blue-600 shadow-sm' : 'text-slate-500'}`}
                  >
                    {t('plugins.config_modal.form_view')}
                  </button>
                </div>
              </div>

              <div className="bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden min-h-[400px] flex flex-col">
                {editorMode === 'code' ? (
                  <CodeMirrorEditor
                    value={configContent}
                    onChange={(value) => setConfigContent(value)}
                    theme={i18n.language === 'zh-CN' ? 'dark' : 'light'}
                  />
                ) : (
                  <div className="flex-1 p-6 overflow-y-auto max-h-[500px] custom-scrollbar">
                    {configData ? (
                      <ConfigForm data={configData} onChange={setConfigData} />
                    ) : (
                      <div className="flex flex-col items-center justify-center py-12 text-slate-500">
                        <AlertTriangle size={32} className="mb-2 opacity-50" />
                        <p>{t('plugins.config_modal.cannot_edit_form')}</p>
                        <p className="text-xs">{t('plugins.config_modal.try_code_view')}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-3 pt-4">
                <button
                  onClick={() => setEditingFile(null)}
                  className="px-6 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl transition-all font-bold"
                >
                  {t('common.cancel')}
                </button>
                <button
                  onClick={handleSaveFile}
                  disabled={isSavingConfig}
                  className="px-8 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl transition-all shadow-lg shadow-blue-600/20 font-bold flex items-center gap-2 disabled:opacity-50"
                >
                  {isSavingConfig ? <Loader2 size={18} className="animate-spin" /> : <SaveIcon size={18} />}
                  {t('common.save')}
                </button>
              </div>
            </div>
          ) : configFiles.length > 0 ? (
            <div className="grid gap-3">
              <p className="text-sm text-slate-500 mb-2 font-medium">{t('plugins.config_modal.available_configs')}</p>
              {configFiles.map((file) => (
                <div
                  key={file}
                  className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-800 rounded-2xl group transition-all"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-white dark:bg-slate-700 rounded-xl shadow-sm">
                      <Settings className="text-slate-400 group-hover:text-blue-500 transition-colors" size={18} />
                    </div>
                    <span className="text-sm font-semibold text-slate-700 dark:text-slate-200 truncate max-w-[200px]">
                      {file.split(/[\\/]/).pop()}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleEditFile(file, 'form')}
                      className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-all"
                      title={t('plugins.config_modal.form_view')}
                    >
                      <FileText size={18} />
                    </button>
                    <button
                      onClick={() => handleEditFile(file, 'code')}
                      className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-all"
                      title={t('plugins.config_modal.code_view')}
                    >
                      <ChevronRight size={18} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-slate-500">
              <div className="p-4 bg-slate-100 dark:bg-slate-800 rounded-full mb-4">
                <Info size={32} className="opacity-20" />
              </div>
              <p className="font-medium">{t('plugins.config_modal.no_config_files')}</p>
            </div>
          )}
        </div>
      </Modal>

      <VersionSelectModal
        isOpen={showVersionModal}
        onClose={() => setShowVersionModal(false)}
        title={t('plugins.version_modal.title') + (selectedPlugin?.name || '')}
        loading={loadingVersions}
        versions={availableVersions}
        currentVersion={selectedPlugin?.version}
        t={t}
        onSelectVersion={(version) => {
          setShowVersionModal(false);
          confirmUpdate({ ...selectedPlugin!, version_latest: version });
        }}
      />

      {/* Notification Toast */}
      <AnimatePresence>
        {showNotification && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.9 }}
            className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-6 py-4 rounded-2xl shadow-2xl ${notificationType === 'success'
              ? 'bg-emerald-500 text-white shadow-emerald-500/20'
              : 'bg-rose-500 text-white shadow-rose-500/20'
              }`}
          >
            {notificationType === 'success' ? <CheckCircle2 size={20} /> : <AlertCircle size={20} />}
            <span className="font-medium">{notificationMsg}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const PluginCard: React.FC<{
  plugin: PluginMetadata;
  t: any;
  onToggle: (p: PluginMetadata) => void;
  onReload: (p: PluginMetadata) => void;
  onUninstall: (p: PluginMetadata) => void;
  onUpdate: (p: PluginMetadata) => void;
  onConfig: (p: PluginMetadata) => void;
  onVersions: (p: PluginMetadata) => void;
  getLocalizedDescription: (desc: string | PluginDescription) => string;
}> = ({ plugin, t, onToggle, onReload, onUninstall, onUpdate, onConfig, onVersions, getLocalizedDescription }) => {
  const isLoaded = plugin.status === 'loaded';
  const hasUpdate = plugin.version_latest && plugin.version && plugin.version !== plugin.version_latest;
  const isSelfWebUI = plugin.id === 'guguwebui';

  const statusInfo = {
    loaded: { color: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-500/10 border-emerald-100 dark:border-emerald-500/20', icon: CheckCircle2 },
    disabled: { color: 'text-rose-500 bg-rose-50 dark:bg-rose-500/10 border-rose-100 dark:border-rose-500/20', icon: Square },
    unloaded: { color: 'text-slate-500 bg-slate-50 dark:bg-slate-500/10 border-slate-100 dark:border-slate-500/20', icon: Play }
  };

  const StatusIcon = statusInfo[plugin.status].icon;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      whileHover={{ y: -4 }}
      className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm hover:shadow-md transition-all flex flex-col"
    >
      <div className="p-6 flex-1 space-y-4">
        {/* Title & Status */}
        <div className="flex items-start gap-4">
          <div className="p-3 bg-blue-500/10 text-blue-500 rounded-2xl shrink-0">
            <Package size={24} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white line-clamp-1">
                {plugin.name}
              </h3>
              <div
                className={`inline-flex items-center justify-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border shrink-0 w-24 text-center ${statusInfo[plugin.status].color}`}
              >
                <StatusIcon size={14} />
                <span className="truncate">{t(`plugins.${plugin.status}`)}</span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <span className="text-xs font-mono text-slate-500 uppercase">{plugin.id}</span>
              <span className="text-slate-300 dark:text-slate-700">•</span>
              <span className="text-xs font-semibold text-blue-600 dark:text-blue-400">v{plugin.version}</span>
              {hasUpdate && (
                <span className="flex items-center gap-1 text-[10px] bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 px-2 py-0.5 rounded-full font-bold">
                  <ArrowUpCircle size={10} />
                  {plugin.version_latest}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Description */}
        <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed line-clamp-2 h-10">
          {getLocalizedDescription(plugin.description) || t('plugins.no_description')}
        </p>

        {/* Metadata Tags */}
        <div className="flex flex-wrap gap-2">
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-400 rounded-lg text-xs">
            <Shield size={14} />
            {plugin.github && plugin.github !== 'None' && plugin.github.trim() !== '' && plugin.author ? (
              <a
                href={plugin.github}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-blue-600 dark:hover:text-blue-400 hover:underline underline-offset-2"
              >
                {plugin.author}
              </a>
            ) : (
              plugin.author || t('common.unknown')
            )}
          </div>
          {plugin.github && plugin.github !== 'None' && plugin.github.trim() !== '' && (
            <a
              href={plugin.github}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-400 rounded-lg text-xs hover:text-blue-500 dark:hover:text-blue-400 transition-colors"
            >
              <Github size={14} />
              GitHub
            </a>
          )}
          {plugin.repository && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs ${plugin.repository.is_official
              ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400'
              : 'bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400'
              }`}>
              <Download size={14} />
              {plugin.repository.name}
            </div>
          )}
        </div>
      </div>

      {/* Action Bar */}
      <div className="px-6 py-4 bg-slate-50/50 dark:bg-slate-900/50 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
        {isSelfWebUI ? (
          <div className="text-xs text-slate-400 dark:text-slate-500 italic">
            {/* 保留占位，避免高度跳变 */}
            {t('plugins.msg.webui_operation_disabled')}
          </div>
        ) : (
          <>
            <div className="flex gap-2">
              <button
                onClick={() => onToggle(plugin)}
                className={`p-2 rounded-xl transition-all ${isLoaded
                  ? 'bg-rose-100 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400 hover:bg-rose-200 text-sm font-semibold flex items-center gap-2 px-3'
                  : 'bg-emerald-100 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-200 text-sm font-semibold flex items-center gap-2 px-3'
                  }`}
                title={isLoaded ? t('plugins.disable') : t('plugins.enable')}
              >
                {isLoaded ? <Square size={16} /> : <Play size={16} />}
                {isLoaded ? t('plugins.disable') : t('plugins.enable')}
              </button>
              <button
                onClick={() => onReload(plugin)}
                disabled={!isLoaded}
                className="p-2 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700 rounded-xl hover:text-blue-500 hover:border-blue-200 dark:hover:border-blue-900/40 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                title={t('plugins.reload')}
              >
                <RotateCw size={18} />
              </button>
              {plugin.config_file && (
                <button
                  onClick={() => onConfig(plugin)}
                  className="p-2 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700 rounded-xl hover:text-blue-500 hover:border-blue-200 dark:hover:border-blue-900/40 transition-all"
                  title={t('plugins.config')}
                >
                  <Settings size={18} />
                </button>
              )}
              <button
                onClick={() => onVersions(plugin)}
                className="px-3 py-1.5 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800/50 rounded-xl hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-all"
                title={t('plugins.versions')}
              >
                <Tag size={14} />
              </button>
            </div>

            <div className="flex gap-2">
              {hasUpdate && (
                <button
                  onClick={() => onUpdate(plugin)}
                  className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold rounded-xl transition-all shadow-lg shadow-amber-500/20 flex items-center gap-2"
                >
                  <ArrowUpCircle size={14} />
                  {t('plugins.update')}
                </button>
              )}
              <button
                onClick={() => onUninstall(plugin)}
                className="p-2 bg-white dark:bg-slate-800 text-rose-500 dark:text-rose-400 border border-slate-200 dark:border-slate-700 rounded-xl hover:bg-rose-50 dark:hover:bg-rose-900/20 hover:border-rose-200 dark:hover:border-rose-900/40 transition-all"
                title={t('plugins.uninstall')}
              >
                <Trash2 size={18} />
              </button>
            </div>
          </>
        )}
      </div>
    </motion.div>
  );
};

const Modal: React.FC<{ isOpen: boolean; onClose: () => void; title: string; children: React.ReactNode; fullWidth?: boolean }> = ({ isOpen, onClose, title, children, fullWidth = false }) => {
  if (!isOpen) return null;
  
  const modalContent = (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" style={{ margin: 0 }}>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/60 backdrop-blur-sm"
      />
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 20 }}
        onClick={(e) => e.stopPropagation()}
        className={`relative bg-white dark:bg-slate-900 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 w-full ${fullWidth ? 'max-w-5xl' : 'max-w-lg'} p-8 z-10`}
      >
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-bold text-slate-900 dark:text-white">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1">
            <X size={24} />
          </button>
        </div>
        {children}
      </motion.div>
    </div>
  );

  return createPortal(modalContent, document.body);
};

const ConfigForm: React.FC<{ data: any; onChange: (data: any) => void }> = ({ data, onChange }) => {
  if (!data || typeof data !== 'object') return null;

  const handleChange = (key: string, value: any) => {
    onChange({ ...data, [key]: value });
  };

  return (
    <div className="space-y-4">
      {Object.entries(data).map(([key, value]: [string, any]) => {
        if (typeof value === 'boolean') {
          return (
            <div key={key} className="flex items-center justify-between p-3 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{key}</span>
              <button
                onClick={() => handleChange(key, !value)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${value ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'}`}
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${value ? 'translate-x-6' : 'translate-x-1'}`} />
              </button>
            </div>
          );
        }
        if (typeof value === 'string' || typeof value === 'number') {
          return (
            <div key={key} className="space-y-1">
              <label className="text-xs font-bold text-slate-500 uppercase ml-1">{key}</label>
              <input
                type={typeof value === 'number' ? 'number' : 'text'}
                value={value}
                onChange={(e) => handleChange(key, typeof value === 'number' ? Number(e.target.value) : e.target.value)}
                className="w-full px-4 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl focus:ring-2 focus:ring-blue-500/50 outline-none transition-all text-sm"
              />
            </div>
          );
        }
        if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
          return (
            <div key={key} className="space-y-2">
              <label className="text-xs font-bold text-slate-500 uppercase ml-1">{key}</label>
              <div className="pl-4 border-l-2 border-slate-100 dark:border-slate-800 ml-1">
                <ConfigForm data={value} onChange={(v) => handleChange(key, v)} />
              </div>
            </div>
          );
        }
        return null;
      })}
    </div>
  );
};

export default LocalPlugins;
