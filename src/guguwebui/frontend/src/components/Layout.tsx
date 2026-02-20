import React, { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  LayoutDashboard, 
  Settings2, 
  Gamepad2, 
  Puzzle, 
  Terminal, 
  Sliders, 
  Info, 
  MessageSquare, 
  Zap, 
  Sun, 
  Moon, 
  LogOut, 
  Menu, 
  ChevronRight, 
  ChevronDown,
  Bell,
  X,
  Languages
} from 'lucide-react'
import api from '../utils/api'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import { fetchNotice, type NoticeData } from '../utils/notice'
import { NoticeModalProvider } from '../context/NoticeModalContext'
import VersionFooter from './VersionFooter'

interface LayoutProps {
  children: React.ReactNode
}

type ServerStatusType = 'online' | 'offline' | 'loading' | 'error'

const statusColors: Record<ServerStatusType, string> = {
  online: 'bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 border-green-100 dark:border-green-900/30',
  offline: 'bg-slate-50 dark:bg-slate-900/20 text-slate-500 dark:text-slate-400 border-slate-100 dark:border-slate-800',
  loading: 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 border-blue-100 dark:border-blue-900/30',
  error: 'bg-rose-50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400 border-rose-100 dark:border-rose-900/30',
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { t, i18n } = useTranslation()
  const { username, nickname, logout } = useAuth()
  const { mode, setMode, label: themeLabel } = useTheme()
  const location = useLocation()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth >= 1024)
  const [pluginPages, setPluginPages] = useState<{ id: string; path: string }[]>([])
  const [isPluginPagesOpen, setIsPluginPagesOpen] = useState(false)
  const [serverStatus, setServerStatus] = useState<ServerStatusType>('loading')
  const [noticeData, setNoticeData] = useState<NoticeData | null>(null)
  const [noticeModalOpen, setNoticeModalOpen] = useState(false)

  useEffect(() => {
    fetchNotice().then(setNoticeData)
  }, [])

  useEffect(() => {
    const fetchServerStatus = async () => {
      try {
        const resp = await api.get('/get_server_status')
        const status = resp.data?.status === 'online' || resp.data?.status === 'offline' ? resp.data.status : 'error'
        setServerStatus(status)
      } catch {
        setServerStatus('error')
      }
    }
    fetchServerStatus()
    const interval = setInterval(fetchServerStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const fetchPluginPages = async () => {
      try {
        const resp = await api.get('/plugins/web_pages')
        setPluginPages(resp.data.pages || [])
      } catch (err) {
        console.error('Failed to fetch registered plugin pages:', err)
      }
    }
    fetchPluginPages()
  }, [])

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 1024) {
        setSidebarOpen(true)
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const changeLanguage = (code: string) => {
    if (i18n.language === code) return
    i18n.changeLanguage(code)
    localStorage.setItem('language', code)
  }

  const noticeModalValue = React.useMemo(
    () => ({ openNoticeModal: () => setNoticeModalOpen(true) }),
    []
  )

  const navItems = [
    { path: '/index', key: 'nav.dashboard', icon: LayoutDashboard },
    { path: '/mcdr', key: 'nav.mcdr_config', icon: Settings2 },
    { path: '/mc', key: 'nav.mc_config', icon: Gamepad2 },
    { path: '/plugins', key: 'nav.local_plugins', icon: Puzzle },
    { path: '/online-plugins', key: 'nav.online_plugins', icon: Puzzle },
    { path: '/terminal', key: 'nav.terminal', icon: Terminal },
    { path: '/chat', key: 'page.chat.header_title', icon: MessageSquare },
    { path: '/settings', key: 'nav.web_settings', icon: Sliders },
    { path: '/about', key: 'nav.about', icon: Info },
  ]

  const activeNavItem = navItems.find(item => item.path === location.pathname) || navItems[0]

  const sidebarVariants = {
    open: { x: 0, transition: { type: 'spring', stiffness: 300, damping: 30 } },
    closed: { x: '-100%', transition: { type: 'spring', stiffness: 300, damping: 30 } }
  } as const

  return (
    <NoticeModalProvider value={noticeModalValue}>
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex transition-colors duration-300">
      {/* Sidebar */}
      <motion.aside
        initial={window.innerWidth >= 1024 ? "open" : "closed"}
        animate={sidebarOpen ? "open" : "closed"}
        variants={sidebarVariants}
        className="fixed inset-y-0 left-0 z-50 w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 flex flex-col shadow-xl lg:shadow-none lg:relative"
      >
        <div className="p-6 flex items-center gap-3">
          <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center text-white shadow-lg shadow-blue-500/30">
            <Zap className="w-6 h-6 fill-current" />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-bold text-slate-900 dark:text-white leading-none truncate">
              {t('app.name')}
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 truncate">
              {t('app.desc')}
            </p>
          </div>
          <button 
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 px-4 py-2 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-2.5 text-sm font-medium rounded-xl transition-all duration-200 relative group ${
                  isActive
                    ? 'text-blue-600 dark:text-blue-400'
                    : 'text-slate-600 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800/50'
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="activeNav"
                    className="absolute inset-0 bg-blue-50 dark:bg-blue-900/20 rounded-xl shadow-sm -z-10"
                    transition={{ type: "spring", stiffness: 380, damping: 30 }}
                  />
                )}
                <item.icon className={`w-5 h-5 transition-transform group-hover:scale-110 ${isActive ? 'text-blue-600 dark:text-blue-400' : ''}`} />
                {t(item.key)}
              </Link>
            )
          })}

          {/* Plugin Web Pages Collapsible */}
          {pluginPages.length > 0 && (
            <div className="pt-2">
              <button
                onClick={() => setIsPluginPagesOpen(!isPluginPagesOpen)}
                className="w-full flex items-center justify-between px-4 py-2 text-xs font-bold text-slate-400 uppercase tracking-wider hover:text-slate-600 dark:hover:text-slate-200 transition-colors group"
              >
                <span className="flex items-center gap-2">
                  <Puzzle size={14} className="group-hover:rotate-12 transition-transform" />
                  {t('plugins.plugin_web_pages', '插件网页')}
                </span>
                <ChevronDown 
                  size={14} 
                  className={`transition-transform duration-200 ${isPluginPagesOpen ? 'rotate-180' : ''}`} 
                />
              </button>
              
              <AnimatePresence>
                {isPluginPagesOpen && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden space-y-1 mt-1 px-2"
                  >
                    {pluginPages.map((page) => {
                      const path = `/plugin-page/${page.id}`
                      const isActive = location.pathname === path
                      return (
                        <Link
                          key={page.id}
                          to={path}
                          className={`flex items-center gap-3 px-4 py-2 text-sm font-medium rounded-xl transition-all duration-200 ${
                            isActive
                              ? 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/20'
                              : 'text-slate-500 hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-slate-800/50'
                          }`}
                        >
                          <span className="w-1.5 h-1.5 rounded-full bg-current opacity-40" />
                          <span className="truncate uppercase text-xs font-mono">{page.id}</span>
                        </Link>
                      )
                    })}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </nav>

        <div className="p-4 border-t border-slate-200 dark:border-slate-800 space-y-3">
          <div className="flex items-center gap-3 px-2">
            {(() => {
              // 判断是否是QQ号（纯数字，长度5-11位）
              const isQQNumber = (str: string | null): boolean => {
                if (!str) return false
                return /^\d{5,11}$/.test(str)
              }
              
              const qqNumber = username && isQQNumber(username) ? username : null
              const avatarUrl = qqNumber ? `https://q1.qlogo.cn/g?b=qq&nk=${qqNumber}&s=100` : null
              
              return avatarUrl ? (
                <div className="w-8 h-8 rounded-full overflow-hidden bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0">
                  <img 
                    src={avatarUrl} 
                    alt={nickname || username || ''} 
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      // 如果头像加载失败，显示首字母
                      const target = e.target as HTMLImageElement
                      target.style.display = 'none'
                      const parent = target.parentElement
                      if (parent) {
                        parent.textContent = (nickname || username)?.charAt(0).toUpperCase() || ''
                        parent.className = 'w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-600 dark:text-slate-400 font-bold text-sm'
                      }
                    }}
                  />
                </div>
              ) : (
                <div className="w-8 h-8 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-600 dark:text-slate-400 font-bold text-sm shrink-0">
                  {(nickname || username)?.charAt(0).toUpperCase()}
                </div>
              )
            })()}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">
                {nickname || username}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {nickname && username !== nickname ? username : t('nav.status_online')}
              </p>
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-2">
            {/* Theme switcher with hover options */}
            <div className="relative group">
              <button
                className="flex items-center justify-center p-2 text-slate-500 hover:text-blue-600 hover:bg-blue-50 dark:text-slate-400 dark:hover:text-blue-400 dark:hover:bg-blue-900/20 rounded-lg transition-colors border border-slate-200 dark:border-slate-800 w-full"
                title={themeLabel}
              >
                {mode === 'dark' ? (
                  <Moon className="w-5 h-5" />
                ) : mode === 'light' ? (
                  <Sun className="w-5 h-5" />
                ) : (
                  <div className="relative w-5 h-5">
                    <Sun className="w-5 h-5 absolute inset-0 opacity-70" />
                    <Moon className="w-3 h-3 absolute -bottom-0.5 -right-0.5 opacity-80" />
                  </div>
                )}
              </button>
              <div className="absolute z-20 bottom-11 left-0 w-32 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-lg opacity-0 scale-95 translate-y-1 group-hover:opacity-100 group-hover:scale-100 group-hover:translate-y-0 transition-all">
                {(['light', 'system', 'dark'] as const).map((opt) => (
                  <button
                    key={opt}
                    onClick={() => setMode(opt)}
                    className={`flex w-full items-center gap-2 px-3 py-1.5 text-xs text-left rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 ${
                      mode === opt
                        ? 'text-blue-600 dark:text-blue-400 font-semibold'
                        : 'text-slate-600 dark:text-slate-300'
                    }`}
                  >
                    {opt === 'light' && <Sun className="w-3.5 h-3.5" />}
                    {opt === 'dark' && <Moon className="w-3.5 h-3.5" />}
                    {opt === 'system' && (
                      <div className="relative w-3.5 h-3.5">
                        <Sun className="w-3.5 h-3.5 absolute inset-0 opacity-70" />
                        <Moon className="w-2.5 h-2.5 absolute -bottom-0.5 -right-0.5 opacity-80" />
                      </div>
                    )}
                    <span>
                      {opt === 'light'
                        ? t('theme.light')
                        : opt === 'dark'
                        ? t('theme.dark')
                        : t('theme.system')}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Language switcher with hover list */}
            <div className="relative group">
              <button
                className="flex items-center justify-center gap-1.5 p-2 text-slate-500 hover:text-blue-600 hover:bg-blue-50 dark:text-slate-400 dark:hover:text-blue-400 dark:hover:bg-blue-900/20 rounded-lg transition-colors border border-slate-200 dark:border-slate-800 w-full"
              >
                <Languages className="w-4 h-4" />
                <span className="text-xs font-bold">
                  {i18n.language === 'zh-CN' ? '中' : 'EN'}
                </span>
              </button>
              <div className="absolute z-20 bottom-11 right-0 w-32 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-lg opacity-0 scale-95 translate-y-1 group-hover:opacity-100 group-hover:scale-100 group-hover:translate-y-0 transition-all">
                {[
                  { code: 'zh-CN', label: '简体中文' },
                  { code: 'en-US', label: 'English' },
                ].map((lang) => (
                  <button
                    key={lang.code}
                    onClick={() => changeLanguage(lang.code)}
                    className={`flex w-full items-center gap-2 px-3 py-1.5 text-xs text-left rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 ${
                      i18n.language === lang.code
                        ? 'text-blue-600 dark:text-blue-400 font-semibold'
                        : 'text-slate-600 dark:text-slate-300'
                    }`}
                  >
                    <span>{lang.label}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
          
          <button
            onClick={logout}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium text-white bg-rose-500 hover:bg-rose-600 dark:bg-rose-500 dark:hover:bg-rose-600 rounded-xl shadow-sm shadow-rose-500/30 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            {t('nav.logout')}
          </button>

          <VersionFooter className="mt-1 text-center" />
        </div>
      </motion.aside>

      {/* Overlay for mobile */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40 lg:hidden"
          />
        )}
      </AnimatePresence>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        {/* Header */}
        <header className="h-16 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200 dark:border-slate-800 flex items-center justify-between px-4 lg:px-8 shrink-0">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="lg:hidden p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
            >
              <Menu className="w-6 h-6" />
            </button>
            <nav className="flex items-center text-sm font-medium text-slate-500">
              <span className="hidden sm:inline hover:text-slate-900 dark:hover:text-white transition-colors cursor-pointer" onClick={() => navigate('/index')}>
                {t('nav.dashboard')}
              </span>
              <ChevronRight className="hidden sm:block w-4 h-4 mx-2 text-slate-300" />
              <span className="text-slate-900 dark:text-white truncate max-w-[150px]">
                {t(activeNavItem.key)}
              </span>
            </nav>
          </div>

          <div className="flex items-center gap-2">
            <div className={`hidden sm:flex items-center px-3 py-1 rounded-full text-xs font-bold border ${statusColors[serverStatus]}`}>
              <span className={`w-1.5 h-1.5 rounded-full mr-2 ${serverStatus === 'online' ? 'bg-green-500 animate-pulse' : serverStatus === 'offline' ? 'bg-slate-400' : serverStatus === 'error' ? 'bg-rose-500' : 'bg-blue-500 animate-pulse'}`} />
              {t(`nav.status_${serverStatus}`)}
            </div>
            <button
              onClick={() => setNoticeModalOpen(true)}
              className="p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors relative"
            >
              <Bell className="w-5 h-5" />
              <span className="absolute top-2 right-2 w-2 h-2 bg-blue-600 rounded-full border-2 border-white dark:border-slate-900" />
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-scroll p-4 lg:p-8">
          <motion.div 
            key={location.pathname}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="max-w-7xl mx-auto"
          >
            {children}
          </motion.div>
        </main>
      </div>

      {/* Notice Modal */}
      {noticeModalOpen && createPortal(
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setNoticeModalOpen(false)}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
          />
          <motion.div
            initial={{ scale: 0.95, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 20 }}
            onClick={(e) => e.stopPropagation()}
            className="relative bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-800 w-full max-w-xl p-6 md:p-8 max-h-[85vh] overflow-y-auto"
          >
            <div className="flex items-center justify-between mb-4 sticky top-0 bg-white dark:bg-slate-900 z-10 pb-3 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white line-clamp-1">
                {noticeData ? noticeData.title : t('page.index.notice')}
              </h3>
              <button
                onClick={() => setNoticeModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                <X size={20} />
              </button>
            </div>
            {noticeData ? (
              <div className="space-y-3">
                <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap">{noticeData.text}</p>
                {noticeData.img && (
                  <img src={noticeData.img} alt="" className="rounded-xl max-w-full max-h-48 object-contain" />
                )}
                {noticeData.fill && (
                  <a
                    href={noticeData.fill}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    {t('page.index.notice_view_detail')}
                  </a>
                )}
              </div>
            ) : (
              <p className="text-sm text-slate-500 dark:text-slate-400">{t('page.index.no_notice')}</p>
            )}
          </motion.div>
        </div>,
        document.body
      )}
    </div>
    </NoticeModalProvider>
  )
}

export default Layout
