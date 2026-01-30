import React, { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import Layout from './components/Layout'
import { useAuth } from './hooks/useAuth'

// 路由级懒加载，将各页面拆成独立 chunk，减小主包体积
const Login = lazy(() => import('./pages/Login'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const MCDRConfig = lazy(() => import('./pages/MCDRConfig'))
const MCConfig = lazy(() => import('./pages/MCConfig'))
const LocalPlugins = lazy(() => import('./pages/LocalPlugins'))
const OnlinePlugins = lazy(() => import('./pages/OnlinePlugins'))
const Terminal = lazy(() => import('./pages/Terminal'))
const Settings = lazy(() => import('./pages/Settings'))
const About = lazy(() => import('./pages/About'))
const Chat = lazy(() => import('./pages/Chat'))
const PlayerChat = lazy(() => import('./pages/PlayerChat'))
const PluginPage = lazy(() => import('./pages/PluginPage'))
const NotFound = lazy(() => import('./pages/NotFound'))

// 独立页面路径（不需要认证）
const PUBLIC_PATHS = ['/login', '/player-chat']

function AppContent() {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()
  const { t } = useTranslation()

  // 如果是独立页面，直接渲染，不等待认证检查
  const isPublicPath = PUBLIC_PATHS.includes(location.pathname)

  // 如果鉴权状态还在加载中，且不是独立页面，先渲染一个简单的加载界面
  if (!isPublicPath && (loading || isAuthenticated === null)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-gray-600 dark:text-gray-300 text-sm">{t('common.checking_login')}</div>
      </div>
    )
  }

  const fallback = (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="text-gray-600 dark:text-gray-300 text-sm">{t('common.notice_loading')}</div>
    </div>
  )

  return (
    <Suspense fallback={fallback}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/player-chat" element={<PlayerChat />} />
        <Route
          path="/*"
          element={
            isAuthenticated ? (
              <Layout>
                <Suspense fallback={fallback}>
                  <Routes>
                    <Route path="/" element={<Navigate to="/index" replace />} />
                    <Route path="/index" element={<Dashboard />} />
                    <Route path="/mcdr" element={<MCDRConfig />} />
                    <Route path="/mc" element={<MCConfig />} />
                    <Route path="/plugins" element={<LocalPlugins />} />
                    <Route path="/online-plugins" element={<OnlinePlugins />} />
                    <Route path="/terminal" element={<Terminal />} />
                    <Route path="/chat" element={<Chat />} />
                    <Route path="/settings" element={<Settings />} />
                    <Route path="/about" element={<About />} />
                    <Route path="/plugin-page/:pluginId" element={<PluginPage />} />
                    <Route path="*" element={<NotFound />} />
                  </Routes>
                </Suspense>
              </Layout>
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />
      </Routes>
    </Suspense>
  )
}

function App() {
  const { i18n } = useTranslation()

  // 同步语言设置到 HTML
  React.useEffect(() => {
    document.documentElement.lang = i18n.language
  }, [i18n.language])

  // 动态获取 base path（支持 fastapi_mcdr 的子路径模式）
  const getBasePath = () => {
    // 如果当前路径包含 /guguwebui，说明使用了 fastapi_mcdr
    const pathname = window.location.pathname
    if (pathname.startsWith('/guguwebui')) {
      return '/guguwebui'
    }
    return ''
  }

  return (
    <BrowserRouter basename={getBasePath()}>
      <AppContent />
    </BrowserRouter>
  )
}

export default App
