import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import 'github-markdown-css/github-markdown.css';
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
  AlertTriangle,
  Tag,
  ChevronLeft,
  FileText,
  BookOpen
} from 'lucide-react';
import api, { isCancel } from '../utils/api';
import { VersionSelectModal } from '../components/VersionSelectModal';
import { NiceSelect } from '../components/NiceSelect';

// --- 接口定义 ---

interface Author {
  name: string;
  link?: string;
}

interface OnlinePlugin {
  id: string;
  name: string;
  description: string | Record<string, string>;
  authors?: Author[]; // JS 对应字段
  author?: string;    // 兼容旧字段
  version: string;
  repository?: string;
  link?: string;
  last_update_time?: string; // JS 对应字段
  last_update?: string;      // 兼容旧字段
  downloads?: number;
  labels?: string[];
  license?: string;
  license_url?: string;
  dependencies?: Record<string, string>;
  readme_url?: string;
}

interface LocalPlugin {
  id: string;
  version: string;
  version_latest: string;
  instance?: any;
}

interface Repository {
  name: string;
  url: string;
  repoId?: number;
}

interface TaskStatus {
  status: string;
  message: string;
  all_messages: string[];
}

interface PluginVersion {
  version: string;
  installed: boolean;
  processing?: boolean;
}

// --- 组件实现 ---

const OnlinePlugins: React.FC = () => {
  const { t, i18n } = useTranslation();

  // 状态管理
  const [plugins, setPlugins] = useState<OnlinePlugin[]>([]);
  const [localPlugins, setLocalPlugins] = useState<LocalPlugin[]>([]);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'name' | 'time' | 'downloads'>('time');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // 分页
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 12; // 缩小卡片后可以显示更多

  // 仓库警告
  const [showRepoWarningModal, setShowRepoWarningModal] = useState(false);
  const [pendingRepo, setPendingRepo] = useState<string | null>(null);

  // 详情模态框逻辑
  const [selectedPlugin, setSelectedPlugin] = useState<OnlinePlugin | null>(null);
  const [pluginHistory, setPluginHistory] = useState<OnlinePlugin[]>([]);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [pluginReadme, setPluginReadme] = useState<string | null>(null);
  const [loadingReadme, setLoadingReadme] = useState(false);

  // 文档弹窗逻辑
  const [showReadmeModal, setShowReadmeModal] = useState(false);
  const [readmeContent, setReadmeContent] = useState<string>('');
  const [loadingReadmeContent, setLoadingReadmeContent] = useState(false);
  const [readmeType, setReadmeType] = useState<'readme' | 'catalogue'>('readme');
  const [readmeUrl, setReadmeUrl] = useState<string>('');
  const [catalogueUrl, setCatalogueUrl] = useState<string>('');

  // 版本选择
  const [showVersionModal, setShowVersionModal] = useState(false);
  const [availableVersions, setAvailableVersions] = useState<PluginVersion[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [versionTargetPluginId, setVersionTargetPluginId] = useState<string>('');
  const [versionTargetPluginName, setVersionTargetPluginName] = useState<string>('');
  const [versionTargetInstalledVersion, setVersionTargetInstalledVersion] = useState<string>('');

  // 安装确认弹窗
  const [showInstallConfirmModal, setShowInstallConfirmModal] = useState(false);
  const [pendingInstallPlugin, setPendingInstallPlugin] = useState<OnlinePlugin | null>(null);

  // 任务状态
  const [installingTaskId, setInstallingTaskId] = useState<string | null>(null);
  const [taskProgress, setTaskProgress] = useState<TaskStatus | null>(null);
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [operatingPluginId, setOperatingPluginId] = useState<string>('');
  const taskPollingRef = useRef(false);

  // 提示通知
  const [showNotification, setShowNotification] = useState(false);
  const [notificationMsg, setNotificationMsg] = useState('');
  const [notificationType, setNotificationType] = useState<'success' | 'error' | 'info'>('success');

  const notify = (msg: string, type: 'success' | 'error' | 'info' = 'success') => {
    setNotificationMsg(msg);
    setNotificationType(type);
    setShowNotification(true);
    setTimeout(() => setShowNotification(false), 3000);
  };

  // 获取本地插件以比对安装状态
  const fetchLocalPlugins = useCallback(async (signal?: AbortSignal) => {
    try {
      const resp = await api.get('/plugins', { signal });
      if (resp.data && resp.data.plugins) {
        setLocalPlugins(resp.data.plugins);
      }
    } catch (error: any) {
      // 忽略取消的请求错误
      if (isCancel(error) || error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
        return;
      }
      console.error('Failed to fetch local plugins:', error);
    }
  }, []);

  const fetchRepositories = useCallback(async (signal?: AbortSignal) => {
    try {
      const resp = await api.get('/get_web_config', { signal });
      const data = resp.data;
      const repos: Repository[] = [
        { name: t('page.settings.repo.official'), url: data.mcdr_plugins_url || '', repoId: 0 },
        { name: t('page.settings.repo.loose_repo'), url: 'https://pfingan-code.github.io/PluginCatalogue/plugins.json', repoId: 1 },
      ];
      if (data.repositories) {
        data.repositories.forEach((r: any, index: number) => {
          if (r.url !== 'https://pfingan-code.github.io/PluginCatalogue/plugins.json') {
            repos.push({ name: r.name, url: r.url, repoId: index + 2 });
          }
        });
      }
      setRepositories(repos);
      if (!selectedRepo && repos.length > 0) setSelectedRepo(repos[0].url);
    } catch (error: any) {
      // 忽略取消的请求错误
      if (isCancel(error) || error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
        return;
      }
      console.error('Failed to fetch repositories:', error);
    }
  }, [t, selectedRepo]);

  const fetchPlugins = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    await fetchLocalPlugins(signal);
    try {
      const resp = await api.get('/online-plugins', {
        params: { repo_url: selectedRepo || undefined },
        signal
      });
      setPlugins(resp.data || []);
    } catch (error: any) {
      // 忽略取消的请求错误
      if (isCancel(error) || error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
        return;
      }
      console.error('Failed to fetch online plugins:', error);
      notify(t('page.online_plugins.msg.load_online_plugins_failed'), 'error');
    } finally {
      setLoading(false);
    }
  }, [selectedRepo, t, fetchLocalPlugins]);

  useEffect(() => {
    // 创建 AbortController 用于取消请求
    const abortController = new AbortController();
    const signal = abortController.signal;

    fetchRepositories(signal);

    return () => {
      // 取消所有进行中的请求
      abortController.abort();
    };
  }, [fetchRepositories]);

  useEffect(() => {
    if (repositories.length > 0) {
      // 创建 AbortController 用于取消请求
      const abortController = new AbortController();
      const signal = abortController.signal;

      fetchPlugins(signal);

      return () => {
        // 取消所有进行中的请求
        abortController.abort();
      };
    }
  }, [selectedRepo, fetchPlugins, repositories.length]);

  // 工具函数：比对版本
  const getPluginStatus = (pluginId: string, remoteVersion: string) => {
    const local = localPlugins.find(p => p.id === pluginId);
    if (!local) return 'not_installed';
    if (local.version === remoteVersion) return 'installed';
    return 'updatable';
  };

  // 轮询任务：若上次请求未完成则跳过本次，稍后再试
  const pollTaskStatus = useCallback(async (taskId: string) => {
    if (taskPollingRef.current) {
      setTimeout(() => pollTaskStatus(taskId), 1000);
      return;
    }
    taskPollingRef.current = true;
    try {
      const resp = await api.get(`/pim/task_status?task_id=${taskId}`);
      if (resp.data.success && resp.data.task_info) {
        const taskInfo = resp.data.task_info;
        const status: TaskStatus = {
          status: taskInfo.status,
          message: taskInfo.message || '',
          all_messages: taskInfo.all_messages || []
        };
        setTaskProgress(status);
        if (status.status === 'completed' || status.status === 'failed') {
          setInstallingTaskId(null);
          if (status.status === 'completed') {
            notify(t('plugins.msg.operation_success', { pluginId: operatingPluginId }), 'success');
            fetchPlugins(); // 成功后刷新
          } else {
            notify(t('plugins.msg.operation_failed_prefix', { pluginId: operatingPluginId, message: status.message }), 'error');
          }
        } else {
          setTimeout(() => pollTaskStatus(taskId), 1000);
        }
      } else {
        setTimeout(() => pollTaskStatus(taskId), 1000);
      }
    } catch (error) {
      setTimeout(() => pollTaskStatus(taskId), 1000);
    } finally {
      taskPollingRef.current = false;
    }
  }, [operatingPluginId, t, fetchPlugins]);

  useEffect(() => {
    if (installingTaskId) {
      pollTaskStatus(installingTaskId);
    }
  }, [installingTaskId, pollTaskStatus]);

  // 从 README / catalogue 链接中推断 GitHub 仓库地址
  const getGithubRepoUrlFromReadme = (url: string): string => {
    try {
      if (!url) return '';

      if (url.includes('raw.githubusercontent.com')) {
        const parts = url.split('/');
        if (parts.length > 5) {
          const username = parts[3];
          const repo = parts[4];
          return `https://github.com/${username}/${repo}`;
        }
      }

      if (url.includes('github.com')) {
        const u = new URL(url);
        const segments = u.pathname.split('/').filter(Boolean);
        if (segments.length >= 2) {
          return `https://github.com/${segments[0]}/${segments[1]}`;
        }
      }
    } catch {
      // ignore parse errors
    }
    return '';
  };

  // 安装逻辑
  const handleInstall = async (pluginId: string, version?: string) => {
    if (pluginId === 'guguwebui') {
      notify(t('plugins.msg.cannot_install_webui'), 'error');
      return;
    }

    try {
      const resp = await api.post('/pim/install_plugin', {
        plugin_id: pluginId,
        version: version,
        repo_url: selectedRepo || undefined
      });
      if (resp.data.success) {
        setInstallingTaskId(resp.data.task_id);
        setOperatingPluginId(pluginId);
        setTaskProgress(null);
        setShowTaskModal(true);
        setShowVersionModal(false);
      } else {
        notify(t('plugins.msg.install_failed_prefix', { message: resp.data.error }), 'error');
      }
    } catch (error) {
      notify(t('plugins.msg.install_failed'), 'error');
    }
  };

  // 版本查询逻辑
  const openVersionSelector = async (plugin: OnlinePlugin) => {
    setVersionTargetPluginId(plugin.id);
    setVersionTargetPluginName(plugin.name);
    const local = localPlugins.find(p => p.id === plugin.id);
    setVersionTargetInstalledVersion(local?.version || '');
    setAvailableVersions([]);
    setLoadingVersions(true);
    setShowVersionModal(true);
    try {
      const resp = await api.get(`/pim/plugin_versions_v2`, {
        params: { plugin_id: plugin.id, repo_url: selectedRepo || undefined }
      });
      if (resp.data.success) {
        const versions = resp.data.versions.map((v: any) => ({
          version: v.version,
          installed: v.version === local?.version,
          prerelease: !!v.prerelease,
          date: v.date || v.release_date || v.time || v.published_at || '',
          downloads: typeof v.downloads === 'number' ? v.downloads : (typeof v.download_count === 'number' ? v.download_count : 0)
        }));
        setAvailableVersions(versions);
      }
    } catch (error) {
      notify(t('page.online_plugins.msg.versions_failed'), 'error');
      setShowVersionModal(false);
    } finally {
      setLoadingVersions(false);
    }
  };

  const openInstallConfirm = (plugin: OnlinePlugin) => {
    if (plugin.id === 'guguwebui') {
      notify(t('plugins.msg.cannot_install_webui'), 'error');
      return;
    }
    setPendingInstallPlugin(plugin);
    setShowInstallConfirmModal(true);
  };

  const closeInstallConfirm = () => {
    setShowInstallConfirmModal(false);
    setPendingInstallPlugin(null);
  };

  // 解析catalogue URL
  const parseCatalogueUrl = (readmeUrl: string): string => {
    try {
      if (readmeUrl.includes('raw.githubusercontent.com')) {
        const urlParts = readmeUrl.split('/');
        const username = urlParts[3];
        const repo = urlParts[4];
        const branch = urlParts[5];
        const lastPart = urlParts[urlParts.length - 1];
        const readmeFileName = lastPart.toLowerCase() === 'readme.md' ? 'README.md' : 'readme.md';
        return `https://raw.githubusercontent.com/${username}/${repo}/${branch}/${readmeFileName}`;
      }
      if (readmeUrl.includes('github.com')) {
        let url = readmeUrl.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/');
        if (url.toLowerCase().endsWith('/readme.md')) {
          const basePath = url.substring(0, url.toLowerCase().lastIndexOf('/readme.md'));
          const readmeFileName = url.toLowerCase().endsWith('/readme.md') ? 'README.md' : 'readme.md';
          url = `${basePath}/${readmeFileName}`;
        }
        return url;
      }
      return '';
    } catch (error) {
      console.warn('解析catalogue_url失败:', error);
      return '';
    }
  };

  const openPluginDetails = async (plugin: OnlinePlugin) => {
    // 处理历史记录
    if (selectedPlugin && selectedPlugin.id !== plugin.id) {
      setPluginHistory(prev => [...prev, selectedPlugin]);
    }

    setSelectedPlugin(plugin);
    setShowDetailModal(true);
    setPluginReadme(null);

    if (!plugin.readme_url) {
      setLoadingReadme(false);
      return;
    }

    setLoadingReadme(true);
    try {
      const resp = await api.get(plugin.readme_url);
      const content = typeof resp.data === 'string' ? resp.data : JSON.stringify(resp.data, null, 2);
      // 只显示前500个字符作为预览
      setPluginReadme(content.length > 500 ? content.substring(0, 500) + '...' : content);
    } catch (error) {
      console.error('Failed to fetch readme:', error);
    } finally {
      setLoadingReadme(false);
    }
  };

  // 打开文档弹窗
  const openReadmeModal = async (plugin: OnlinePlugin) => {
    if (!plugin.readme_url) {
      notify(t('page.online_plugins.msg.no_readme'), 'info');
      return;
    }

    setReadmeUrl(plugin.readme_url);
    const catalogue = parseCatalogueUrl(plugin.readme_url);
    setCatalogueUrl(catalogue);
    
    // 默认打开catalogue文档（如果存在），否则打开readme
    const defaultType = catalogue ? 'catalogue' : 'readme';
    setReadmeType(defaultType);
    setShowReadmeModal(true);
    setReadmeContent('');
    setLoadingReadmeContent(true);

    try {
      const url = defaultType === 'readme' ? plugin.readme_url : catalogue;
      const resp = await api.get(url);
      setReadmeContent(typeof resp.data === 'string' ? resp.data : JSON.stringify(resp.data, null, 2));
    } catch (error) {
      console.error('Failed to fetch readme content:', error);
      notify(t('page.online_plugins.msg.load_doc_failed'), 'error');
    } finally {
      setLoadingReadmeContent(false);
    }
  };

  // 切换文档类型
  const switchReadmeType = async (type: 'readme' | 'catalogue') => {
    if (readmeType === type) return;
    
    setReadmeType(type);
    setLoadingReadmeContent(true);

    try {
      const url = type === 'readme' ? readmeUrl : catalogueUrl;
      if (!url) {
        const docType = type === 'readme' 
          ? t('page.online_plugins.readme_doc')
          : t('page.online_plugins.catalogue_doc');
        throw new Error(t('page.online_plugins.msg.doc_not_found', { docType }));
      }
      const resp = await api.get(url);
      setReadmeContent(typeof resp.data === 'string' ? resp.data : JSON.stringify(resp.data, null, 2));
    } catch (error) {
      console.error(`Error switching to ${type}:`, error);
      notify(t('page.online_plugins.msg.load_doc_failed'), 'error');
    } finally {
      setLoadingReadmeContent(false);
    }
  };

  const goBackInHistory = () => {
    const prev = pluginHistory[pluginHistory.length - 1];
    if (prev) {
      setPluginHistory(prev => prev.slice(0, -1));
      openPluginDetails(prev);
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
      const authorsStr = (p.authors?.map(a => a.name).join(' ') || p.author || '').toLowerCase();

      return p.name.toLowerCase().includes(q) ||
        p.id.toLowerCase().includes(q) ||
        localizedDesc.includes(q) ||
        authorsStr.includes(q);
    });

    result.sort((a, b) => {
      let comparison = 0;
      if (sortBy === 'name') {
        comparison = a.name.localeCompare(b.name);
      } else if (sortBy === 'time') {
        const timeA = new Date(a.last_update_time || a.last_update || 0).getTime();
        const timeB = new Date(b.last_update_time || b.last_update || 0).getTime();
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
    const repo = repositories.find(r => r.url === url);
    const today = new Date().toISOString().slice(0, 10);
    const storedDate = localStorage.getItem('skipRepoWarningDate');
    const skipRepoWarningToday = storedDate === today;
    if (repo && repo.repoId !== 0 && !skipRepoWarningToday) {
      setPendingRepo(url);
      setShowRepoWarningModal(true);
    } else {
      setSelectedRepo(url);
      setCurrentPage(1);
    }
  };

  const githubRepoUrl = useMemo(
    () => getGithubRepoUrlFromReadme(readmeUrl || catalogueUrl || ''),
    [readmeUrl, catalogueUrl]
  );

  return (
    <div className="space-y-6 pb-12 animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
            <Database className="text-purple-500" size={28} />
            {t('nav.online_plugins')}
          </h1>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            {t('page.online_plugins.title')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-56">
            <NiceSelect
              value={selectedRepo}
              onChange={(val) => handleRepoChange(val)}
              options={repositories.map((repo) => ({
                value: repo.url,
                label: repo.name,
              }))}
            />
          </div>
          <button
            onClick={() => fetchPlugins()}
            disabled={loading}
            className="p-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-colors shadow-sm"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-4 items-center justify-between bg-white dark:bg-slate-900 p-3 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div className="relative w-full md:w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
          <input
            type="text"
            placeholder={t('page.online_plugins.search')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:ring-2 focus:ring-purple-500/50 outline-none transition-all"
          />
        </div>
        <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-lg shrink-0">
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
              className={`px-3 py-1 rounded-md text-[11px] font-bold transition-all flex items-center gap-1.5 ${sortBy === sort
                ? 'bg-white dark:bg-slate-700 text-purple-600 dark:text-purple-400 shadow-sm'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
            >
              {t(`page.online_plugins.sort_${sort}`)}
              {sortBy === sort && (
                sortOrder === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Plugin Grid */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-24">
          <Loader2 className="w-10 h-10 text-purple-500 animate-spin mb-4" />
          <p className="text-sm text-slate-500 animate-pulse">{t('page.online_plugins.loading')}</p>
        </div>
      ) : paginatedPlugins.length > 0 ? (
        <div className="space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <AnimatePresence>
              {paginatedPlugins.map((plugin) => (
                <OnlinePluginCard
                  key={plugin.id}
                  plugin={plugin}
                  status={getPluginStatus(plugin.id, plugin.version)}
                  t={t}
                  onInstall={() => openInstallConfirm(plugin)}
                  onSelectVersion={() => openVersionSelector(plugin)}
                  onViewDetails={() => openPluginDetails(plugin)}
                  onOpenReadme={() => openReadmeModal(plugin)}
                  getLocalizedDescription={getLocalizedDescription}
                />
              ))}
            </AnimatePresence>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex justify-center items-center gap-2 pt-2">
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                className="p-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg disabled:opacity-50 hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-all shadow-sm"
              >
                <ArrowRight size={16} className="rotate-180" />
              </button>
              <div className="flex items-center gap-1">
                <span className="text-xs font-bold text-slate-500">{currentPage} / {totalPages}</span>
              </div>
              <button
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                className="p-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg disabled:opacity-50 hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-all shadow-sm"
              >
                <ArrowRight size={16} />
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-20 bg-white dark:bg-slate-900 rounded-3xl border border-dashed border-slate-200 dark:border-slate-800">
          <Puzzle className="w-12 h-12 text-slate-300 mb-3" />
          <p className="text-sm text-slate-500">{t('page.online_plugins.empty')}</p>
        </div>
      )}

      {/* Task Progress Modal */}
      <Modal
        isOpen={showTaskModal}
        onClose={() => !installingTaskId && setShowTaskModal(false)}
        title={t('plugins.install_modal.install_progress') + ': ' + operatingPluginId}
      >
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-600 dark:text-slate-400">
              {taskProgress && (taskProgress.status === 'completed' || taskProgress.status === 'failed') ? t('plugins.install_modal.completed') : t('plugins.install_modal.processing')}
            </span>
          </div>
          <div className="bg-slate-950 rounded-xl p-4 font-mono text-[10px] text-slate-300 h-60 overflow-y-auto space-y-1 custom-scrollbar shadow-inner">
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
              className="px-6 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 text-slate-700 dark:text-slate-200 rounded-xl transition-colors text-sm font-bold"
            >
              {t('common.confirm')}
            </button>
          </div>
        </div>
      </Modal>

      {/* Version Choice Modal */}
      <VersionSelectModal
        isOpen={showVersionModal}
        onClose={() => setShowVersionModal(false)}
        title={t('plugins.version_modal.title') + (versionTargetPluginName || '')}
        loading={loadingVersions}
        versions={availableVersions}
        currentVersion={versionTargetInstalledVersion || undefined}
        t={t}
        onSelectVersion={(version) => handleInstall(versionTargetPluginId, version)}
      />

      {/* Install Confirm Modal */}
      <Modal
        isOpen={showInstallConfirmModal}
        onClose={closeInstallConfirm}
        title={t('page.online_plugins.install_confirm_title')}
      >
        <div className="space-y-5">
          <div className="text-sm text-slate-600 dark:text-slate-400">
            {t('page.online_plugins.installing_plugin')}
            <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
              {pendingInstallPlugin?.id || ''}
            </span>
          </div>

          <div className="space-y-3">
            <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">
              {t('page.online_plugins.select_install_method')}
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => {
                  if (!pendingInstallPlugin) return;
                  closeInstallConfirm();
                  openVersionSelector(pendingInstallPlugin);
                }}
                className="flex-1 px-5 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl transition-all font-bold text-sm"
              >
                {t('page.online_plugins.choose_version')}
              </button>
              <button
                onClick={() => {
                  if (!pendingInstallPlugin) return;
                  closeInstallConfirm();
                  handleInstall(pendingInstallPlugin.id);
                }}
                className="flex-1 px-5 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/20 font-bold text-sm"
              >
                {t('page.online_plugins.install_latest')}
              </button>
            </div>
          </div>
        </div>
      </Modal>

      {/* Detail Modal */}
      <Modal
        isOpen={showDetailModal}
        onClose={() => setShowDetailModal(false)}
        title={selectedPlugin?.name || ''}
      >
        <div className="space-y-5">
          {/* Top Info Bar */}
          <div className="flex items-center gap-2 mb-2">
            {pluginHistory.length > 0 && (
              <button
                onClick={goBackInHistory}
                className="p-1 px-2 flex items-center gap-1 text-xs text-purple-600 bg-purple-100 rounded-lg hover:bg-purple-200 transition-colors"
                title={t('common.back')}
              >
                <ChevronLeft size={16} />
                {t('common.back')}
              </button>
            )}
          </div>

          <div className="flex flex-wrap gap-2 items-center">
            <button
              onClick={() => selectedPlugin && openVersionSelector(selectedPlugin)}
              className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 dark:bg-slate-800 rounded-xl text-xs font-bold hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
            >
              <Package size={14} />
              <span>v{selectedPlugin?.version}</span>
            </button>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 dark:bg-slate-800 rounded-xl text-xs font-bold">
              <Calendar size={14} />
              <span>{selectedPlugin?.last_update_time || selectedPlugin?.last_update}</span>
            </div>
          </div>

          {/* Authors */}
          <div className="space-y-1">
            <h4 className="flex items-center gap-2 text-xs font-bold text-slate-500 uppercase tracking-wider">
              <Users size={14} />
              {t('page.online_plugins.authors')}
            </h4>
            <div className="flex flex-wrap gap-2">
              {selectedPlugin?.authors ? selectedPlugin.authors.map(a => (
                a.link ? (
                  <a
                    key={a.name}
                    href={a.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-2 py-1 bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400 rounded-lg text-xs font-medium flex items-center gap-1 hover:underline whitespace-nowrap"
                  >
                    {a.name}
                    <ExternalLink size={10} />
                  </a>
                ) : (
                  <span
                    key={a.name}
                    className="px-2 py-1 bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400 rounded-lg text-xs font-medium whitespace-nowrap"
                  >
                    {a.name}
                  </span>
                )
              )) : selectedPlugin?.author ? (
                selectedPlugin.link ? (
                  <a
                    href={selectedPlugin.link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-2 py-1 bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400 rounded-lg text-xs font-medium flex items-center gap-1 hover:underline whitespace-nowrap"
                  >
                    {selectedPlugin.author}
                    <ExternalLink size={10} />
                  </a>
                ) : (
                  <span className="text-xs text-slate-600">{selectedPlugin.author}</span>
                )
              ) : (
                <span className="text-xs text-slate-400">{t('common.unknown')}</span>
              )}
            </div>
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <h4 className="font-bold text-slate-900 dark:text-white flex items-center gap-2 text-sm">
              <Info size={16} />
              {t('page.online_plugins.description')}
            </h4>
            <div className="text-slate-600 dark:text-slate-400 text-xs leading-relaxed max-h-24 overflow-y-auto">
              {selectedPlugin && getLocalizedDescription(selectedPlugin.description)}
            </div>
          </div>

          {/* Dependencies */}
          {selectedPlugin?.dependencies && Object.keys(selectedPlugin.dependencies).length > 0 && (
            <div className="space-y-1.5">
              <h4 className="flex items-center gap-2 text-xs font-bold text-slate-500 uppercase tracking-wider">
                <Tag size={14} />
                {t('page.online_plugins.dependencies')}
              </h4>
              <div className="flex flex-wrap gap-2">
                {Object.entries(selectedPlugin.dependencies).map(([id, ver]) => {
                  const depPlugin = plugins.find(p => p.id === id);
                  return (
                    <button
                      key={id}
                      onClick={() => depPlugin && openPluginDetails(depPlugin)}
                      className={`px-2 py-1 rounded-lg text-xs font-medium border transition-all flex items-center gap-1.5 ${depPlugin
                        ? 'border-slate-200 dark:border-slate-700 hover:border-purple-500 text-slate-700 dark:text-slate-300'
                        : 'border-amber-100 bg-amber-50 text-amber-600 cursor-default'
                        }`}
                    >
                      {id}
                      <span className="opacity-50">{ver}</span>
                      {depPlugin && <ArrowRight size={10} />}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Readme Section - 详情弹窗中仅作纯文本预览，不再渲染 Markdown */}
          {selectedPlugin?.readme_url && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="font-bold text-slate-900 dark:text-white flex items-center gap-2 text-sm">
                  <ShieldCheck size={16} />
                  {t('page.online_plugins.readme')}
                </h4>
                {/* 如果不是 Markdown 文档，给出纯文本提示 */}
                {!(selectedPlugin.readme_url.toLowerCase().endsWith('.md')) && (
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">
                    {t('page.online_plugins.msg.no_readme_plain')}
                  </span>
                )}
              </div>
              <div className="bg-slate-50 dark:bg-slate-800/60 rounded-xl p-4 min-h-32 max-h-60 overflow-y-auto custom-scrollbar border border-slate-100 dark:border-slate-800 relative">
                {loadingReadme ? (
                  <div className="flex justify-center py-8">
                    <Loader2 className="animate-spin text-purple-500" />
                  </div>
                ) : pluginReadme ? (
                  <>
                    <pre className="whitespace-pre-wrap break-words text-[11px] text-slate-700 dark:text-slate-300 font-mono leading-relaxed">
                      {pluginReadme}
                    </pre>
                    {pluginReadme.endsWith('...') && (
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-slate-50 dark:from-slate-800/60 to-transparent h-16 flex items-end justify-center pb-2">
                        <button
                          onClick={() => openReadmeModal(selectedPlugin)}
                          className="text-xs font-bold text-purple-600 dark:text-purple-400 hover:text-purple-700 dark:hover:text-purple-300 flex items-center gap-1"
                        >
                          {t('page.online_plugins.view_full_doc')}
                          <BookOpen size={12} />
                        </button>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-slate-500 text-center py-8 italic text-xs">{t('page.online_plugins.msg.load_doc_failed')}</p>
                )}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800">
            <div className="flex items-center gap-4">
              {selectedPlugin?.link && (
                <a
                  href={selectedPlugin.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-purple-500 hover:text-purple-600 flex items-center gap-1.5 text-xs font-bold"
                >
                  <Github size={14} />
                  GitHub
                  <ExternalLink size={10} />
                </a>
              )}
              {selectedPlugin?.license && (
                <div className="flex items-center gap-1.5 text-xs text-slate-500">
                  <ShieldCheck size={14} />
                  {selectedPlugin.license}
                </div>
              )}
            </div>
            <button
              onClick={() => selectedPlugin && handleInstall(selectedPlugin.id)}
              className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white font-bold rounded-xl text-sm transition-all shadow-lg shadow-purple-500/20 flex items-center gap-2"
            >
              <Download size={16} />
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
            className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3 rounded-xl shadow-2xl ${notificationType === 'success' ? 'bg-emerald-500 text-white shadow-emerald-500/20' :
              notificationType === 'info' ? 'bg-blue-500 text-white shadow-blue-500/20' :
                'bg-rose-500 text-white shadow-rose-500/20'
              }`}
          >
            {notificationType === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
            <span className="text-sm font-bold">{notificationMsg}</span>
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
            <p className="text-sm text-slate-600 dark:text-slate-400 text-center leading-relaxed">
              {t('page.online_plugins.third_repo_warning_lead')}
            </p>
          </div>

          <div className="space-y-3 text-sm text-slate-700 dark:text-slate-300">
            <p className="font-semibold">{t('page.online_plugins.note')}</p>
            <ul className="list-disc pl-5 space-y-1">
              <li>{t('page.online_plugins.third_repo_warning_p1')}</li>
              <li>{t('page.online_plugins.third_repo_warning_p2')}</li>
              <li>{t('page.online_plugins.third_repo_warning_p3')}</li>
              <li>{t('page.online_plugins.third_repo_warning_p4')}</li>
            </ul>
            <p>{t('page.online_plugins.third_repo_warning_conclusion')}</p>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={() => setShowRepoWarningModal(false)}
              className="flex-1 px-6 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl transition-all font-bold text-sm"
            >
              {t('common.cancel')}
            </button>
            <button
              onClick={() => {
                if (pendingRepo) {
                  setSelectedRepo(pendingRepo);
                  setCurrentPage(1);
                  setShowRepoWarningModal(false);
                  localStorage.setItem('skipRepoWarningDate', new Date().toISOString().slice(0, 10));
                }
              }}
              className="flex-1 px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/20 font-bold text-sm"
            >
              {t('page.online_plugins.repo_continue')}
            </button>
          </div>
        </div>
      </Modal>

      {/* Readme Document Modal */}
      <Modal
        isOpen={showReadmeModal}
        onClose={() => setShowReadmeModal(false)}
        title={t('page.online_plugins.readme')}
        maxWidthClassName="max-w-6xl"
      >
        <div className="space-y-4">
          {/* 文档类型切换按钮 + GitHub 跳转按钮 */}
          {(catalogueUrl || githubRepoUrl) && (
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 pb-3">
              <div className="flex gap-2">
                {catalogueUrl && (
                  <>
                    <button
                      onClick={() => switchReadmeType('catalogue')}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                        readmeType === 'catalogue'
                          ? 'bg-purple-600 text-white shadow-md'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                      }`}
                    >
                      {t('page.online_plugins.catalogue_doc')}
                    </button>
                    <button
                      onClick={() => switchReadmeType('readme')}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                        readmeType === 'readme'
                          ? 'bg-purple-600 text-white shadow-md'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                      }`}
                    >
                      {t('page.online_plugins.readme_doc')}
                    </button>
                  </>
                )}
              </div>
              {githubRepoUrl && (
                <a
                  href={githubRepoUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-purple-600 dark:hover:text-purple-400"
                >
                  <Github size={14} />
                  {t('page.online_plugins.github_repo')}
                  <ExternalLink size={10} />
                </a>
              )}
            </div>
          )}

          {/* 文档内容（渲染区域滚动） */}
          <div className="bg-slate-50 dark:bg-slate-800/60 rounded-xl p-6 min-h-[400px] max-h-[60vh] overflow-y-auto custom-scrollbar border border-slate-100 dark:border-slate-800">
            {loadingReadmeContent ? (
              <div className="flex flex-col items-center justify-center py-16">
                <Loader2 className="animate-spin text-purple-500 mb-4" size={32} />
                <p className="text-slate-500 text-sm">
                  {readmeType === 'catalogue'
                    ? t('page.online_plugins.loading_catalogue')
                    : t('page.online_plugins.loading_readme')
                  }
                </p>
              </div>
            ) : readmeContent ? (
              <div className="markdown-body bg-transparent" style={{ padding: 0 }}>
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                  {readmeContent}
                </ReactMarkdown>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16">
                <FileText className="text-slate-400 mb-4" size={48} />
                <p className="text-slate-500 text-sm">{t('page.online_plugins.msg.load_doc_failed')}</p>
              </div>
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
};

// --- 子组件：插件卡片 (高度优化版) ---

const OnlinePluginCard: React.FC<{
  plugin: OnlinePlugin;
  status: 'not_installed' | 'installed' | 'updatable'; // 扩展状态
  t: any;
  onInstall: () => void;
  onSelectVersion: () => void;
  onViewDetails: () => void;
  onOpenReadme: () => void;
  getLocalizedDescription: (desc: string | Record<string, string>) => string;
}> = ({ plugin, status, t, onInstall, onSelectVersion, onViewDetails, onOpenReadme, getLocalizedDescription }) => {
  const isSelfWebUI = plugin.id === 'guguwebui';

  // 格式化时间
  const formatDate = (dateString?: string) => {
    if (!dateString) return '';
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
      return dateString;
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      whileHover={{ y: -3 }}
      className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm hover:shadow-md transition-all flex flex-col group relative"
    >
      <div className="p-4 flex-1 space-y-3">
        {/* Header: Icon & Downloads */}
        <div className="flex items-start justify-between">
          <div className="p-2 bg-purple-50 dark:bg-purple-900/10 text-purple-600 dark:text-purple-400 rounded-xl group-hover:bg-purple-600 group-hover:text-white transition-all">
            <Package size={20} />
          </div>
          {plugin.downloads !== undefined && (
            <div className="flex items-center gap-1 text-[10px] font-bold text-slate-400">
              <Download size={10} />
              {plugin.downloads}
            </div>
          )}
        </div>

        {/* Title & Info */}
        <div className="space-y-0.5">
          <h3 className="text-base font-bold text-slate-900 dark:text-white line-clamp-1 group-hover:text-purple-600 transition-colors">
            {plugin.name}
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => { e.stopPropagation(); onSelectVersion(); }}
              className="text-[10px] text-slate-400 font-mono hover:text-purple-500 transition-colors"
            >
              v{plugin.version}
            </button>
            <span className="text-[10px] text-slate-300 dark:text-slate-600">|</span>
            <span className="text-[10px] text-slate-400 font-mono line-clamp-1 max-w-[100px]">{plugin.id}</span>
          </div>
        </div>

        {/* Description - 限制为单行以减少垂直空间 */}
        <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-1 h-4">
          {getLocalizedDescription(plugin.description) || t('plugins.no_description')}
        </p>

        {/* Authors on card */}
        {(plugin.authors && plugin.authors.length > 0) || plugin.author ? (
          <div className="flex items-center gap-1 text-[10px] text-slate-500">
            <Users size={10} className="opacity-70" />
            {plugin.authors && plugin.authors.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {plugin.authors.slice(0, 2).map((a) =>
                  a.link ? (
                    <a
                      key={a.name}
                      href={a.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="hover:text-purple-500 underline-offset-2 hover:underline"
                    >
                      {a.name}
                    </a>
                  ) : (
                    <span key={a.name}>{a.name}</span>
                  )
                )}
                {plugin.authors.length > 2 && (
                  <span className="text-slate-400">…</span>
                )}
              </div>
            ) : plugin.author ? (
              plugin.link ? (
                <a
                  href={plugin.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="truncate max-w-[120px] hover:text-purple-500 underline-offset-2 hover:underline"
                >
                  {plugin.author}
                </a>
              ) : (
                <span className="truncate max-w-[120px]">{plugin.author}</span>
              )
            ) : null}
          </div>
        ) : null}

        {/* 时间和协议信息 */}
        <div className="flex items-center gap-3 text-[10px] text-slate-400">
          {(plugin.last_update_time || plugin.last_update) && (
            <div className="flex items-center gap-1">
              <Calendar size={10} />
              <span>{formatDate(plugin.last_update_time || plugin.last_update)}</span>
            </div>
          )}
          {plugin.license && (
            <div className="flex items-center gap-1">
              <ShieldCheck size={10} />
              <span>{plugin.license}</span>
            </div>
          )}
        </div>

        {/* Labels - 紧凑显示 */}
        <div className="flex flex-wrap gap-1">
          {plugin.labels?.slice(0, 2).map(label => (
            <span key={label} className="text-[9px] bg-slate-50 dark:bg-slate-800 text-slate-400 px-2 py-0.5 rounded-md font-medium">
              #{label}
            </span>
          ))}
        </div>
      </div>

      {/* Compact Footer */}
      <div className="px-4 py-2.5 bg-slate-50/50 dark:bg-slate-900/50 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
        <button
          onClick={onViewDetails}
          className="text-[11px] font-bold text-slate-400 hover:text-purple-500 transition-colors flex items-center gap-1"
        >
          {t('page.online_plugins.details')}
          <ArrowRight size={12} />
        </button>

        {!isSelfWebUI && (
          <div className="flex items-center gap-2">
            {plugin.link && (
              <a
                href={plugin.link}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-purple-500 transition-colors"
                title="GitHub"
              >
                <Github size={12} />
              </a>
            )}

            {plugin.readme_url && (
              <button
                onClick={(e) => { e.stopPropagation(); onOpenReadme(); }}
                className="px-3 py-1 rounded-lg text-[10px] font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                {t('page.online_plugins.view_doc')}
              </button>
            )}

            {status === 'updatable' && (
              <button
                onClick={onInstall}
                className="text-[10px] font-bold bg-amber-500 hover:bg-amber-600 text-white px-2.5 py-1 rounded-lg transition-transform active:scale-95"
              >
                {t('plugins.status.updatable')}
              </button>
            )}

            <button
              onClick={status === 'installed' ? undefined : onInstall}
              disabled={status === 'installed'}
              className={`px-3 py-1.5 rounded-lg text-[11px] font-bold transition-all flex items-center gap-1.5 ${
                status === 'installed'
                  ? 'bg-emerald-500 text-white cursor-default'
                  : 'bg-purple-600 text-white shadow-md shadow-purple-500/20 hover:scale-110 active:scale-95'
              }`}
              title={status === 'installed' ? t('common.installed') : t('common.install')}
            >
              {status === 'installed' ? (
                t('common.installed')
              ) : (
                <>
                  <Download size={12} />
                  {t('common.install')}
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
};

// --- 重用通用 Modal 组件 ---

const Modal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  maxWidthClassName?: string;
}> = ({ isOpen, onClose, title, children, maxWidthClassName }) => {
  if (!isOpen) return null;
  
  const modalContent = (
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
        onClick={(e) => e.stopPropagation()}
        className={`relative bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 w-full ${maxWidthClassName || 'max-w-xl'} p-6 md:p-8 max-h-[85vh] overflow-y-auto custom-scrollbar`}
      >
        <div className="flex items-center justify-between mb-4 sticky top-0 bg-white dark:bg-slate-900 z-10 pb-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-xl font-bold text-slate-900 dark:text-white line-clamp-1">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
            <X size={20} />
          </button>
        </div>
        {children}
      </motion.div>
    </div>
  );

  return createPortal(modalContent, document.body);
};

export default OnlinePlugins;