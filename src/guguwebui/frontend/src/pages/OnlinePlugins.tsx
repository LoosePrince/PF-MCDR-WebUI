import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Puzzle,
  Search,
  Download,
  ExternalLink,
  Info,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
  Github,
  Package,
  Database,
  ShieldCheck,
  ArrowUp,
  ArrowDown,
  RefreshCw,
  Users,
  Calendar,
  ArrowRight,
  AlertTriangle
} from 'lucide-react';
import axios from 'axios';

interface OnlinePlugin {
  id: string;
  name: string;
  description: string | Record<string, string>;
  author: string;
  version: string;
  repository?: string;
  link?: string;
  last_update?: string;
  downloads?: number;
  labels?: string[];
  license?: string;
  dependencies?: Record<string, string>;
  readme_url?: string;
}

interface Repository {
  name: string;
  url: string;
}

interface TaskStatus {
  completed: boolean;
  success: boolean;
  message: string;
  output: string[];
}

const OnlinePlugins: React.FC = () => {
  const { t, i18n } = useTranslation();

  // State
  const [plugins, setPlugins] = useState<OnlinePlugin[]>([]);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'name' | 'time' | 'downloads'>('time');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  // Repository warning
  const [showRepoWarningModal, setShowRepoWarningModal] = useState(false);
  const [pendingRepo, setPendingRepo] = useState<string | null>(null);

  // Plugin Details Modal
  const [selectedPlugin, setSelectedPlugin] = useState<OnlinePlugin | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [pluginReadme, setPluginReadme] = useState<string | null>(null);
  const [loadingReadme, setLoadingReadme] = useState(false);

  // Task state
  const [installingTaskId, setInstallingTaskId] = useState<string | null>(null);
  const [taskProgress, setTaskProgress] = useState<TaskStatus | null>(null);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [operatingPluginId, setOperatingPluginId] = useState<string>('');

  // Notification state
  const [showNotification, setShowNotification] = useState(false);
  const [notificationMsg, setNotificationMsg] = useState('');
  const [notificationType, setNotificationType] = useState<'success' | 'error'>('success');

  const notify = (msg: string, type: 'success' | 'error') => {
    setNotificationMsg(msg);
    setNotificationType(type);
    setShowNotification(true);
    setTimeout(() => setShowNotification(false), 3000);
  };

  const fetchRepositories = useCallback(async () => {
    try {
      const resp = await axios.get('/api/get_web_config');
      const repos: Repository[] = [
        { name: t('page.settings.repo.official'), url: '' },
        { name: t('page.settings.repo.loose_repo'), url: 'https://looseprince.github.io/Plugin-Catalogue/plugins.json' },
        ...resp.data.repositories.map((r: any) => ({ name: r.name, url: r.url }))
      ];
      setRepositories(repos);
      // Don't auto-select if already selected
      if (!selectedRepo && repos.length > 0) setSelectedRepo(repos[0].url);
    } catch (error) {
      console.error('Failed to fetch repositories:', error);
    }
  }, [t]);

  const fetchPlugins = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await axios.get('/api/online-plugins', {
        params: { repo_url: selectedRepo || undefined }
      });
      setPlugins(resp.data || []);
    } catch (error) {
      console.error('Failed to fetch online plugins:', error);
      notify(t('page.online_plugins.msg.load_online_plugins_failed'), 'error');
    } finally {
      setLoading(false);
    }
  }, [selectedRepo, t]);

  useEffect(() => {
    fetchRepositories();
  }, [fetchRepositories]);

  useEffect(() => {
    if (repositories.length > 0) {
      fetchPlugins();
    }
  }, [selectedRepo, fetchPlugins, repositories.length]);

  const pollTaskStatus = useCallback(async (taskId: string) => {
    try {
      const resp = await axios.get(`/api/pim/task_status?task_id=${taskId}`);
      if (resp.data.success) {
        const status = resp.data.task_info;
        setTaskProgress(status);
        if (status.completed) {
          setInstallingTaskId(null);
          if (status.success) {
            notify(t('plugins.msg.operation_success', { pluginId: operatingPluginId }), 'success');
          } else {
            notify(t('plugins.msg.operation_failed_prefix', { pluginId: operatingPluginId, message: status.message }), 'error');
          }
        } else {
          setTimeout(() => pollTaskStatus(taskId), 1000);
        }
      }
    } catch (error) {
      console.error('Failed to poll task status:', error);
      setInstallingTaskId(null);
      notify(t('plugins.msg.task_query_error_continue'), 'error');
    }
  }, [operatingPluginId, t]);

  useEffect(() => {
    if (installingTaskId) {
      pollTaskStatus(installingTaskId);
    }
  }, [installingTaskId, pollTaskStatus]);

  const handleInstall = async (plugin: OnlinePlugin) => {
    if (plugin.id === 'guguwebui') {
      notify(t('plugins.msg.cannot_install_webui'), 'error');
      return;
    }

    try {
      const resp = await axios.post('/api/pim/install_plugin', {
        plugin_id: plugin.id
      });
      if (resp.data.success) {
        setInstallingTaskId(resp.data.task_id);
        setOperatingPluginId(plugin.id);
        setTaskProgress(null);
        setShowTaskModal(true);
      } else {
        notify(t('plugins.msg.install_failed_prefix', { message: resp.data.error }), 'error');
      }
    } catch (error) {
      notify(t('plugins.msg.install_failed'), 'error');
    }
  };

  const openPluginDetails = async (plugin: OnlinePlugin) => {
    setSelectedPlugin(plugin);
    setShowDetailModal(true);
    setPluginReadme(null);

    if (!plugin.readme_url) {
      setLoadingReadme(false);
      return;
    }

    setLoadingReadme(true);
    try {
      // Fetch readme directly from the URL provided in metadata
      const readmeUrl = (plugin as any).readme_url;
      const resp = await axios.get(readmeUrl);
      if (typeof resp.data === 'string') {
        setPluginReadme(resp.data);
      } else if (typeof resp.data === 'object') {
        // If it's JSON, it might be the content or some other structure
        setPluginReadme(JSON.stringify(resp.data, null, 2));
      }
    } catch (error) {
      console.error('Failed to fetch readme:', error);
      // Ignore readme fetch error
    } finally {
      setLoadingReadme(false);
    }
  };

  const getLocalizedDescription = (desc: string | Record<string, string>) => {
    if (typeof desc === 'string') return desc;
    const currentLang = i18n.language.toLowerCase().replace('-', '_');
    return desc[currentLang] || desc['zh_cn'] || desc['en_us'] || Object.values(desc)[0] || '';
  };

  const sortedAndFilteredPlugins = useMemo(() => {
    let result = plugins.filter(p => {
      const q = searchQuery.toLowerCase();
      const localizedDesc = (typeof p.description === 'object'
        ? Object.values(p.description).join(' ')
        : p.description || '').toLowerCase();

      return p.name.toLowerCase().includes(q) ||
        p.id.toLowerCase().includes(q) ||
        localizedDesc.includes(q) ||
        (p.author && p.author.toLowerCase().includes(q));
    });

    result.sort((a, b) => {
      let comparison = 0;
      if (sortBy === 'name') {
        comparison = a.name.localeCompare(b.name);
      } else if (sortBy === 'time') {
        const timeA = new Date(a.last_update || 0).getTime();
        const timeB = new Date(b.last_update || 0).getTime();
        comparison = timeA - timeB;
      } else if (sortBy === 'downloads') {
        comparison = (a.downloads || 0) - (b.downloads || 0);
      }
      return sortOrder === 'asc' ? comparison : -comparison;
    });

    return result;
  }, [plugins, searchQuery, sortBy, sortOrder]);

  const paginatedPlugins = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage;
    return sortedAndFilteredPlugins.slice(start, start + itemsPerPage);
  }, [sortedAndFilteredPlugins, currentPage]);

  const totalPages = Math.ceil(sortedAndFilteredPlugins.length / itemsPerPage);

  const handleRepoChange = (url: string) => {
    if (url !== '' && localStorage.getItem('skipRepoWarning') !== 'true') {
      setPendingRepo(url);
      setShowRepoWarningModal(true);
    } else {
      setSelectedRepo(url);
      setCurrentPage(1);
    }
  };

  const confirmRepoChange = () => {
    if (pendingRepo !== null) {
      setSelectedRepo(pendingRepo);
      setCurrentPage(1);
      setShowRepoWarningModal(false);
      localStorage.setItem('skipRepoWarning', 'true');
    }
  };

  return (
    <div className="space-y-8 pb-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
            <Database className="text-purple-500" />
            {t('nav.online_plugins')}
          </h1>
          <p className="mt-1 text-slate-600 dark:text-slate-400">
            {t('page.online_plugins.title')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 p-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-sm">
            <select
              value={selectedRepo}
              onChange={(e) => handleRepoChange(e.target.value)}
              className="bg-transparent border-none outline-none text-sm font-medium px-3 py-1 cursor-pointer"
            >
              {repositories.map((repo) => (
                <option key={repo.url} value={repo.url}>{repo.name}</option>
              ))}
            </select>
          </div>
          <button
            onClick={fetchPlugins}
            disabled={loading}
            className="p-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-colors shadow-sm"
          >
            <RefreshCw size={20} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-4 items-center justify-between bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div className="relative w-full md:w-96">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
          <input
            type="text"
            placeholder={t('page.online_plugins.search')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-purple-500/50 outline-none transition-all"
          />
        </div>
        <div className="flex gap-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-lg shrink-0">
          {(['name', 'time', 'downloads'] as const).map((sort) => (
            <button
              key={sort}
              onClick={() => {
                if (sortBy === sort) {
                  setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
                } else {
                  setSortBy(sort);
                  setSortOrder(sort === 'name' ? 'asc' : 'desc');
                }
              }}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${sortBy === sort
                ? 'bg-white dark:bg-slate-700 text-purple-600 dark:text-purple-400 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
            >
              {t(`page.online_plugins.sort_${sort}`)}
              {sortBy === sort && (
                sortOrder === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Plugin Grid */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-24">
          <Loader2 className="w-12 h-12 text-purple-500 animate-spin mb-4" />
          <p className="text-slate-500 animate-pulse">{t('page.online_plugins.loading')}</p>
        </div>
      ) : paginatedPlugins.length > 0 ? (
        <div className="space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <AnimatePresence mode="popLayout">
              {paginatedPlugins.map((plugin) => (
                <OnlinePluginCard
                  key={plugin.id}
                  plugin={plugin}
                  t={t}
                  onInstall={handleInstall}
                  onViewDetails={openPluginDetails}
                  getLocalizedDescription={getLocalizedDescription}
                />
              ))}
            </AnimatePresence>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex justify-center items-center gap-2 pt-4">
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                className="p-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl disabled:opacity-50 hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-all shadow-sm"
              >
                <ArrowRight size={18} className="rotate-180" />
              </button>

              <div className="flex items-center gap-1 mx-2">
                {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => {
                  // Show current page, first, last, and neighbors
                  if (
                    page === 1 ||
                    page === totalPages ||
                    (page >= currentPage - 1 && page <= currentPage + 1)
                  ) {
                    return (
                      <button
                        key={page}
                        onClick={() => setCurrentPage(page)}
                        className={`w-10 h-10 rounded-xl text-sm font-bold transition-all shadow-sm ${currentPage === page
                          ? 'bg-purple-600 text-white'
                          : 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/80'
                          }`}
                      >
                        {page}
                      </button>
                    );
                  } else if (
                    (page === 2 && currentPage > 3) ||
                    (page === totalPages - 1 && currentPage < totalPages - 2)
                  ) {
                    return <span key={page} className="px-1 text-slate-400">...</span>;
                  }
                  return null;
                })}
              </div>

              <button
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                className="p-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl disabled:opacity-50 hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-all shadow-sm"
              >
                <ArrowRight size={18} />
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-24 bg-white dark:bg-slate-900 rounded-3xl border border-dashed border-slate-200 dark:border-slate-800">
          <Puzzle className="w-16 h-16 text-slate-300 mb-4" />
          <p className="text-slate-500">{t('page.online_plugins.empty')}</p>
        </div>
      )}

      {/* Task Progress Modal */}
      <Modal
        isOpen={showTaskModal}
        onClose={() => !installingTaskId && setShowTaskModal(false)}
        title={t('plugins.install_modal.install_progress') + operatingPluginId}
      >
        <div className="space-y-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-slate-600 dark:text-slate-400">
              {taskProgress?.completed ? t('plugins.install_modal.completed') : t('plugins.install_modal.processing')}
            </span>
          </div>

          <div className="bg-slate-950 rounded-2xl p-4 font-mono text-xs text-slate-300 h-64 overflow-y-auto space-y-1 custom-scrollbar">
            {taskProgress?.output?.map((line, i) => (
              <div key={i} className="break-all whitespace-pre-wrap">{line}</div>
            )) || <div className="text-slate-500 animate-pulse">{t('plugins.install_modal.waiting_logs')}</div>}
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

      {/* Detail Modal */}
      <Modal
        isOpen={showDetailModal}
        onClose={() => setShowDetailModal(false)}
        title={selectedPlugin?.name || ''}
      >
        <div className="space-y-6">
          <div className="flex flex-wrap gap-4 items-center">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 dark:bg-slate-800 rounded-xl text-sm font-medium">
              <Package size={16} />
              <span>v{selectedPlugin?.version}</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 dark:bg-slate-800 rounded-xl text-sm font-medium">
              <Users size={16} />
              <span>{selectedPlugin?.author}</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 dark:bg-slate-800 rounded-xl text-sm font-medium">
              <Calendar size={16} />
              <span>{selectedPlugin?.last_update}</span>
            </div>
          </div>

          <div className="space-y-2">
            <h4 className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Info size={18} />
              {t('page.online_plugins.description')}
            </h4>
            <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
              {selectedPlugin && getLocalizedDescription(selectedPlugin.description)}
            </p>
          </div>

          <div className="space-y-2">
            <h4 className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <ShieldCheck size={18} />
              {t('page.online_plugins.readme')}
            </h4>
            <div className="bg-slate-50 dark:bg-slate-800/60 rounded-2xl p-4 min-h-32 max-h-96 overflow-y-auto">
              {loadingReadme ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="animate-spin text-purple-500" />
                </div>
              ) : pluginReadme ? (
                <div className="prose dark:prose-invert max-w-none text-sm" dangerouslySetInnerHTML={{ __html: pluginReadme }} />
              ) : (
                <p className="text-slate-500 text-center py-8 italic">{t('page.online_plugins.msg.load_doc_failed')}</p>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between pt-4">
            {selectedPlugin?.link && (
              <a
                href={selectedPlugin.link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-purple-500 hover:text-purple-600 flex items-center gap-1 text-sm font-bold"
              >
                <Github size={16} />
                {t('page.online_plugins.github_repo')}
                <ExternalLink size={14} />
              </a>
            )}
            <button
              onClick={() => selectedPlugin && handleInstall(selectedPlugin)}
              className="px-8 py-2.5 bg-purple-600 hover:bg-purple-700 text-white font-bold rounded-2xl transition-all shadow-lg shadow-purple-500/20 flex items-center gap-2"
            >
              <Download size={18} />
              {t('common.install')}
            </button>
          </div>
        </div>
      </Modal>

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

      {/* Repo Warning Modal */}
      <Modal
        isOpen={showRepoWarningModal}
        onClose={() => setShowRepoWarningModal(false)}
        title={t('page.online_plugins.third_repo_warning_title')}
      >
        <div className="space-y-6">
          <div className="flex flex-col items-center justify-center py-4">
            <div className="p-4 bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 rounded-full mb-4">
              <AlertTriangle size={48} />
            </div>
            <p className="text-slate-600 dark:text-slate-400 text-center leading-relaxed">
              {t('page.online_plugins.third_repo_warning_lead')}
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => setShowRepoWarningModal(false)}
              className="flex-1 px-6 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl transition-all font-bold"
            >
              {t('common.cancel')}
            </button>
            <button
              onClick={confirmRepoChange}
              className="flex-1 px-6 py-2.5 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/20 font-bold"
            >
              {t('common.confirm')}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

const OnlinePluginCard: React.FC<{
  plugin: OnlinePlugin;
  t: any;
  onInstall: (p: OnlinePlugin) => void;
  onViewDetails: (p: OnlinePlugin) => void;
  getLocalizedDescription: (desc: string | Record<string, string>) => string;
}> = ({ plugin, t, onInstall, onViewDetails, getLocalizedDescription }) => {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      whileHover={{ y: -5 }}
      className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm hover:shadow-lg transition-all flex flex-col group"
    >
      <div className="p-6 flex-1 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div className="p-3 bg-purple-100 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400 rounded-2xl group-hover:scale-110 transition-transform">
            <Package size={24} />
          </div>
          {plugin.downloads !== undefined && (
            <div className="flex items-center gap-1.5 px-3 py-1 bg-slate-100 dark:bg-slate-800 rounded-full text-[10px] font-bold text-slate-500">
              <Download size={12} />
              {plugin.downloads}
            </div>
          )}
        </div>

        <div>
          <h3 className="text-xl font-bold text-slate-900 dark:text-white line-clamp-1">{plugin.name}</h3>
          <p className="text-xs text-slate-500 mt-1 font-mono">{plugin.id} • v{plugin.version}</p>
        </div>

        <p className="text-sm text-slate-600 dark:text-slate-400 line-clamp-2 h-10 leading-relaxed">
          {getLocalizedDescription(plugin.description) || t('plugins.no_description')}
        </p>

        <div className="flex flex-wrap gap-2 pt-2">
          {plugin.labels?.slice(0, 3).map(label => (
            <span key={label} className="text-[10px] bg-slate-50 dark:bg-slate-800 text-slate-500 px-2.5 py-1 rounded-lg font-medium">
              {label}
            </span>
          ))}
        </div>
      </div>

      <div className="px-6 py-4 bg-slate-50/50 dark:bg-slate-900/50 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
        <button
          onClick={() => onViewDetails(plugin)}
          className="text-sm font-bold text-slate-600 dark:text-slate-400 hover:text-purple-500 transition-colors flex items-center gap-1"
        >
          {t('page.online_plugins.details')}
          <ArrowRight size={16} />
        </button>
        <button
          onClick={() => onInstall(plugin)}
          className="p-2.5 bg-purple-600 hover:bg-purple-700 text-white rounded-xl shadow-lg shadow-purple-500/20 transition-all hover:scale-110 active:scale-95"
          title={t('common.install')}
        >
          <Download size={18} />
        </button>
      </div>
    </motion.div>
  );
};

const Modal: React.FC<{ isOpen: boolean; onClose: () => void; title: string; children: React.ReactNode }> = ({ isOpen, onClose, title, children }) => {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
      />
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 20 }}
        className="relative bg-white dark:bg-slate-900 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-800 w-full max-w-2xl p-8 max-h-[90vh] overflow-y-auto custom-scrollbar"
      >
        <div className="flex items-center justify-between mb-6 sticky top-0 bg-white dark:bg-slate-900 z-10 pb-4 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-2xl font-bold text-slate-900 dark:text-white">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800">
            <X size={24} />
          </button>
        </div>
        {children}
      </motion.div>
    </div>
  );
};

export default OnlinePlugins;
