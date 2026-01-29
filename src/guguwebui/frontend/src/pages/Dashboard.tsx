import React, { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  Play, 
  RotateCw, 
  Square, 
  Server, 
  Users, 
  Tag, 
  Lock, 
  Puzzle, 
  Settings2, 
  Sliders, 
  ChevronRight,
  Activity,
  Clock,
  Info,
  X
} from 'lucide-react'
import axios from 'axios'

interface ServerStatus {
  status: 'online' | 'offline' | 'loading' | 'error'
  version: string
  players: string
}

interface RconStatus {
  rcon_enabled: boolean
  rcon_connected: boolean
}

interface PipPackage {
  name: string
  version: string
}

type NotificationType = 'success' | 'error'

const Dashboard: React.FC = () => {
  const { t } = useTranslation()
  const [serverStatus, setServerStatus] = useState<ServerStatus>({
    status: 'loading',
    version: '',
    players: '0/0',
  })
  const [rconStatus, setRconStatus] = useState<RconStatus>({
    rcon_enabled: false,
    rcon_connected: false,
  })
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [webVersion, setWebVersion] = useState<string | null>(null)
  const [systemTime, setSystemTime] = useState<string>('')

  const [pipPackages, setPipPackages] = useState<PipPackage[]>([])
  const [loadingPipPackages, setLoadingPipPackages] = useState<boolean>(true)
  const [pipOutput, setPipOutput] = useState<string[]>([])
  const [pipOutputVisible, setPipOutputVisible] = useState<boolean>(false)
  const [showInstallPipModal, setShowInstallPipModal] = useState<boolean>(false)
  const [newPipPackage, setNewPipPackage] = useState<string>('')
  const [installingPip, setInstallingPip] = useState<boolean>(false)
  const [uninstallingPip, setUninstallingPip] = useState<boolean>(false)

  const [showNotification, setShowNotification] = useState<boolean>(false)
  const [notificationMessage, setNotificationMessage] = useState<string>('')
  const [notificationType, setNotificationType] = useState<NotificationType>('success')

  const [showRconSetupModal, setShowRconSetupModal] = useState<boolean>(false)
  const [settingUpRcon, setSettingUpRcon] = useState<boolean>(false)

  const fetchStatus = useCallback(async () => {
    try {
      const statusResp = await axios.get('/api/get_server_status')
      setServerStatus(statusResp.data)
      
      const rconResp = await axios.get('/api/get_rcon_status')
      if (rconResp.data.status === 'success') {
        setRconStatus({
          rcon_enabled: rconResp.data.rcon_enabled,
          rcon_connected: rconResp.data.rcon_connected,
        })
      }
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error)
      setServerStatus(prev => ({ ...prev, status: 'error' }))
    }
  }, [])

  const showNotificationMessage = useCallback((message: string, type: NotificationType) => {
    setNotificationMessage(message)
    setNotificationType(type)
    setShowNotification(true)
    setTimeout(() => {
      setShowNotification(false)
    }, 5000)
  }, [])

  const refreshPipPackages = useCallback(async () => {
    setLoadingPipPackages(true)
    try {
      const { data } = await axios.get('/api/pip/list')
      if (data.status === 'success') {
        setPipPackages(data.packages || [])
      } else {
        showNotificationMessage(
          `${t('page.index.pip_list_failed_prefix')}${data.message || t('common.unknown')}`,
          'error'
        )
        setPipPackages([])
      }
    } catch (error: any) {
      console.error('Error fetching pip packages:', error)
      showNotificationMessage(
        t('page.index.pip_list_failed'),
        'error'
      )
      setPipPackages([])
    } finally {
      setLoadingPipPackages(false)
    }
  }, [showNotificationMessage, t])

  const pollPipTaskStatus = useCallback(async (taskId: string) => {
    try {
      const { data } = await axios.get('/api/pip/task_status', {
        params: { task_id: taskId },
      })

      if (data.status === 'success') {
        if (Array.isArray(data.output) && data.output.length > 0) {
          setPipOutput(data.output)
        }

        if (data.completed) {
          if (data.success) {
            showNotificationMessage(
              t('page.index.pip_op_succeeded'),
              'success'
            )
          } else {
            showNotificationMessage(
              t('page.index.pip_op_failed'),
              'error'
            )
          }
          setInstallingPip(false)
          setUninstallingPip(false)
          setNewPipPackage('')
          refreshPipPackages()
          return
        }

        setTimeout(() => {
          pollPipTaskStatus(taskId)
        }, 1000)
      } else {
        setPipOutput(prev => [
          ...prev,
          `${t('page.index.get_task_status_failed_prefix')}${data.message || t('common.unknown')}`,
        ])
        setInstallingPip(false)
        setUninstallingPip(false)
      }
    } catch (error: any) {
      console.error('Error checking pip task status:', error)
      setPipOutput(prev => [
        ...prev,
        `${t('page.index.get_task_status_failed_prefix')}${error.message}`,
      ])
      setInstallingPip(false)
      setUninstallingPip(false)
    }
  }, [refreshPipPackages, showNotificationMessage, t])

  const startPipOperation = useCallback(async (url: string, pkgName: string | null, installing: boolean) => {
    if (!url) return
    if (pkgName !== null && !pkgName.trim()) return

    if (installing) {
      setInstallingPip(true)
    } else {
      setUninstallingPip(true)
    }
    setPipOutput([])

    try {
      const payload = pkgName ? { package: pkgName } : {}
      const { data } = await axios.post(url, payload)

      if (data.status !== 'success' || !data.task_id) {
        setPipOutput(prev => [
          ...prev,
          `${t('page.index.operation_failed_prefix')}${data.message || t('common.unknown')}`,
        ])
        showNotificationMessage(
          t('page.index.pip_op_failed'),
          'error'
        )
        setInstallingPip(false)
        setUninstallingPip(false)
        return
      }

      const taskId: string = data.task_id
      pollPipTaskStatus(taskId)
    } catch (error: any) {
      console.error('Error starting pip operation:', error)
      setPipOutput(prev => [
        ...prev,
        `${t('page.index.operation_failed_prefix')}${error.message}`,
      ])
      showNotificationMessage(
        t('page.index.pip_op_failed'),
        'error'
      )
      setInstallingPip(false)
      setUninstallingPip(false)
    }
  }, [pollPipTaskStatus, showNotificationMessage, t])

  const handleInstallPip = useCallback(async () => {
    if (!newPipPackage.trim() || installingPip) return
    setShowInstallPipModal(false)
    await startPipOperation('/api/pip/install', newPipPackage.trim(), true)
  }, [installingPip, newPipPackage, startPipOperation])

  const handleUninstallPip = useCallback(async (pkgName: string) => {
    if (!pkgName || uninstallingPip) return
    await startPipOperation('/api/pip/uninstall', pkgName, false)
  }, [startPipOperation, uninstallingPip])

  const setupRcon = useCallback(async () => {
    try {
      setSettingUpRcon(true)
      const { data } = await axios.post('/api/setup_rcon')

      if (data.status === 'success') {
        setShowRconSetupModal(false)
        await fetchStatus()
        showNotificationMessage(
          t('page.mcdr.rcon.setup_success_msg'),
          'success'
        )
      } else {
        showNotificationMessage(
          `${t('page.mcdr.rcon.setup_failed_prefix')}${data.message || ''}`,
          'error'
        )
      }
    } catch (error) {
      console.error('Setup RCON error:', error)
      showNotificationMessage(
        t('page.mcdr.rcon.setup_error'),
        'error'
      )
    } finally {
      setSettingUpRcon(false)
    }
  }, [fetchStatus, showNotificationMessage, t])

  const fetchWebVersion = useCallback(async () => {
    try {
      // 使用 plugin_id 精确获取指定插件信息，替代 detail=false 的用法
      const { data } = await axios.get('/api/plugins', { params: { plugin_id: 'guguwebui' } })
      const plugins = Array.isArray(data.plugins) ? data.plugins : []
      const webui = plugins[0]
      if (webui && webui.version) {
        setWebVersion(webui.version)
        return
      }
      setWebVersion(t('page.index.unknown'))
    } catch (error) {
      console.error('Failed to fetch WebUI version:', error)
      setWebVersion(t('common.unknown'))
    }
  }, [t])

  useEffect(() => {
    fetchStatus()
    const timer = setInterval(fetchStatus, 10000)
    fetchWebVersion()
    setSystemTime(new Date().toLocaleString())
    const clockTimer = setInterval(() => {
      setSystemTime(new Date().toLocaleString())
    }, 1000)
    refreshPipPackages()
    return () => {
      clearInterval(timer)
      clearInterval(clockTimer)
    }
  }, [fetchStatus, fetchWebVersion, refreshPipPackages])

  useEffect(() => {
    if (pipOutput.length > 0) {
      setPipOutputVisible(true)
    }
  }, [pipOutput])

  const handleAction = async (action: 'start' | 'stop' | 'restart') => {
    setActionLoading(action)
    try {
      const { data } = await axios.post('/api/control_server', { action })
      if (data.status === 'success') {
        const actionText =
          action === 'start'
            ? t('page.index.action_start')
            : action === 'stop'
            ? t('page.index.action_stop')
            : t('page.index.action_restart')
        const msg =
          data.message ||
          `${t('page.index.control_sent_prefix')}${actionText}${t(
            'page.index.control_sent_suffix'
          )}`
        showNotificationMessage(msg, 'success')
      } else {
        showNotificationMessage(
          `${t('page.index.control_failed_prefix')}${data.message || t('common.unknown')}`,
          'error'
        )
      }
      setTimeout(fetchStatus, 2000)
    } catch (error) {
      console.error(`Failed to ${action} server:`, error)
      showNotificationMessage(
        t('page.index.control_error'),
        'error'
      )
    } finally {
      setActionLoading(null)
    }
  }

  const statusColors = {
    online: 'text-green-500 bg-green-50 dark:bg-green-900/20 border-green-100 dark:border-green-900/30',
    offline: 'text-slate-500 bg-slate-50 dark:bg-slate-900/20 border-slate-100 dark:border-slate-800',
    loading: 'text-blue-500 bg-blue-50 dark:bg-blue-900/20 border-blue-100 dark:border-blue-900/30',
    error: 'text-rose-500 bg-rose-50 dark:bg-rose-900/20 border-rose-100 dark:border-rose-900/30',
  }

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1
      }
    }
  }

  const itemVariants = {
    hidden: { y: 20, opacity: 0 },
    visible: { y: 0, opacity: 1 }
  }

  return (
    <>
      <motion.div 
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="space-y-8"
      >
      {/* Welcome Hero */}
      <motion.div 
        variants={itemVariants}
        className="relative overflow-hidden bg-white dark:bg-slate-900 rounded-3xl p-8 border border-slate-200 dark:border-slate-800 shadow-sm"
      >
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-2">
            <h1 className="text-3xl font-bold text-slate-900 dark:text-white">
              {t('nav.dashboard')}
            </h1>
            <p className="text-slate-500 dark:text-slate-400 max-w-lg">
              {t('app.desc')} - {t('page.index.webui_running')}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => handleAction('start')}
              disabled={serverStatus.status === 'online' || !!actionLoading}
              className="px-6 py-2.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-all shadow-lg shadow-green-500/20 flex items-center gap-2 group"
            >
              {actionLoading === 'start' ? (
                <RotateCw className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4 fill-current group-hover:scale-110 transition-transform" />
              )}
              {t('page.index.start')}
            </button>
            <button
              onClick={() => handleAction('restart')}
              disabled={serverStatus.status === 'offline' || !!actionLoading}
              className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-all shadow-lg shadow-blue-500/20 flex items-center gap-2 group"
            >
              {actionLoading === 'restart' ? (
                <RotateCw className="w-4 h-4 animate-spin" />
              ) : (
                <RotateCw className="w-4 h-4 group-hover:rotate-180 transition-transform duration-500" />
              )}
              {t('page.index.restart')}
            </button>
            <button
              onClick={() => handleAction('stop')}
              disabled={serverStatus.status === 'offline' || !!actionLoading}
              className="px-6 py-2.5 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-all shadow-lg shadow-rose-500/20 flex items-center gap-2 group"
            >
              {actionLoading === 'stop' ? (
                <RotateCw className="w-4 h-4 animate-spin" />
              ) : (
                <Square className="w-4 h-4 fill-current group-hover:scale-110 transition-transform" />
              )}
              {t('page.index.stop')}
            </button>
          </div>
        </div>
        
        {/* Decorative background element */}
        <motion.div 
          animate={{ 
            scale: [1, 1.2, 1],
            opacity: [0.05, 0.08, 0.05] 
          }}
          transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
          className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 bg-blue-500/5 rounded-full blur-3xl" 
        />
        <motion.div 
          animate={{ 
            scale: [1.2, 1, 1.2],
            opacity: [0.05, 0.08, 0.05] 
          }}
          transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
          className="absolute bottom-0 left-0 -ml-16 -mb-16 w-64 h-64 bg-purple-500/5 rounded-full blur-3xl" 
        />
      </motion.div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Status Card */}
        <motion.div variants={itemVariants} className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-2xl text-slate-600 dark:text-slate-400">
              <Server className="w-6 h-6" />
            </div>
            <div className={`px-3 py-1 rounded-full text-xs font-bold border ${statusColors[serverStatus.status]}`}>
              {t(`nav.status_${serverStatus.status}`)}
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{t('page.index.server')}</p>
            <p className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {serverStatus.status === 'online' ? t('page.index.running') : t('page.index.stopped')}
            </p>
          </div>
        </motion.div>

        {/* Players Card */}
        <motion.div variants={itemVariants} className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-2xl text-slate-600 dark:text-slate-400">
              <Users className="w-6 h-6" />
            </div>
            {serverStatus.status === 'online' && (
              <Activity className="w-4 h-4 text-green-500 animate-pulse" />
            )}
          </div>
          <div>
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{t('page.index.online_players')}</p>
            <p className="text-xl font-bold text-slate-900 dark:text-white mt-1">
              {serverStatus.players || '0/0'}
            </p>
          </div>
        </motion.div>

        {/* Version Card */}
        <motion.div variants={itemVariants} className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-2xl text-slate-600 dark:text-slate-400">
              <Tag className="w-6 h-6" />
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
              {t('page.index.server_version')}
            </p>
            <p className="text-xl font-bold text-slate-900 dark:text-white mt-1 truncate">
              {serverStatus.version.replace('Version: ', '') || t('page.index.unknown')}
            </p>
          </div>
        </motion.div>

        {/* RCON Status Card */}
        <motion.div variants={itemVariants} className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-2xl text-slate-600 dark:text-slate-400">
              <Lock className="w-6 h-6" />
            </div>
            <div
              className={`px-3 py-1 rounded-full text-xs font-bold border ${
                statusColors[rconStatus.rcon_connected ? 'online' : 'offline']
              }`}
            >
              {rconStatus.rcon_connected ? t('page.index.rcon_connected') : t('page.index.rcon_disconnected')}
            </div>
          </div>
          <div className="space-y-2">
            <div>
              <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
                RCON {t('page.index.connection_status')}
              </p>
              <p className="text-xl font-bold text-slate-900 dark:text-white mt-1">
                {rconStatus.rcon_enabled ? t('page.index.rcon_enabled') : t('page.index.rcon_disabled')}
              </p>
            </div>
            {!rconStatus.rcon_connected && (
              <button
                onClick={() => setShowRconSetupModal(true)}
                disabled={settingUpRcon}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold transition-colors"
              >
                {settingUpRcon ? (
                  <>
                    <RotateCw className="w-3 h-3 animate-spin" />
                    {t('page.mcdr.rcon.setting_up')}
                  </>
                ) : (
                  <>
                    <Puzzle className="w-3 h-3" />
                    {t('page.mcdr.rcon.setup_button')}
                  </>
                )}
              </button>
            )}
          </div>
        </motion.div>
      </div>

      {/* Feature Navigation */}
      <div className="space-y-4">
        <h2 className="text-xl font-bold text-slate-900 dark:text-white px-2">
          {t('page.index.quick_nav')}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[
            { key: 'plugins_mgmt', icon: Puzzle, color: 'bg-blue-500', path: '/plugins' },
            { key: 'mcdr_config', icon: Settings2, color: 'bg-purple-500', path: '/mcdr' },
            { key: 'mc_config', icon: Sliders, color: 'bg-emerald-500', path: '/mc' },
            { key: 'online_plugins', icon: Puzzle, color: 'bg-amber-500', path: '/online-plugins' },
          ].map((item) => (
            <motion.a
              key={item.key}
              href={item.path}
              variants={itemVariants}
              whileHover={{ y: -5 }}
              className="group bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm hover:shadow-md hover:border-blue-500/30 dark:hover:border-blue-500/30 transition-all flex items-center gap-4"
            >
              <div className={`p-4 ${item.color} rounded-2xl text-white shadow-lg shadow-${item.color.split('-')[1]}-500/20 group-hover:scale-110 transition-transform`}>
                <item.icon className="w-6 h-6" />
              </div>
              <div className="flex-1">
                <h3 className="font-bold text-slate-900 dark:text-white">{t(`page.index.${item.key}`)}</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400">{t(`page.index.${item.key}_desc`)}</p>
              </div>
              <ChevronRight className="w-5 h-5 text-slate-300 group-hover:text-blue-500 transition-colors" />
            </motion.a>
          ))}
        </div>
      </div>

      {/* System info & pip management in two columns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* System info & RCON */}
        <motion.div
          variants={itemVariants}
          className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4"
        >
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            {t('page.index.system_info')}
          </h2>
          <div className="space-y-3">
            <div className="flex items-center p-3 rounded-2xl bg-slate-50 dark:bg-slate-800/60">
              <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center text-blue-600 dark:text-blue-400">
                <Info className="w-5 h-5" />
              </div>
              <div className="ml-4">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                  {t('page.index.webui_version')}
                </p>
                <p className="text-sm font-semibold text-slate-900 dark:text-white mt-0.5">
                  {webVersion ?? t('common.notice_loading')}
                </p>
              </div>
            </div>

            <div className="flex items-center p-3 rounded-2xl bg-slate-50 dark:bg-slate-800/60">
              <div className="w-10 h-10 rounded-full bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
                <Clock className="w-5 h-5" />
              </div>
              <div className="ml-4">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                  {t('page.index.system_time')}
                </p>
                <p className="text-sm font-semibold text-slate-900 dark:text-white mt-0.5">
                  {systemTime}
                </p>
              </div>
            </div>

            <div className="flex items-center p-3 rounded-2xl bg-slate-50 dark:bg-slate-800/60">
              <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center text-amber-600 dark:text-amber-400">
                <Lock className="w-5 h-5" />
              </div>
              <div className="ml-4">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                  {t('page.index.security_status')}
                </p>
                <p className="text-sm font-semibold text-slate-900 dark:text-white mt-0.5">
                  {t('page.index.logged_in')}
                </p>
              </div>
            </div>
          </div>
        </motion.div>

        {/* pip management */}
        <motion.div
          variants={itemVariants}
          className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">
              {t('page.index.pip_mgmt')}
            </h2>
            <div className="flex gap-2">
              <button
                onClick={refreshPipPackages}
                className="px-3 py-1.5 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded-full text-xs font-semibold flex items-center gap-1.5 hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
              >
                <RotateCw className="w-3 h-3" />
                {t('page.index.refresh')}
              </button>
              <button
                onClick={() => setShowInstallPipModal(true)}
                className="px-3 py-1.5 bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 rounded-full text-xs font-semibold flex items-center gap-1.5 hover:bg-emerald-100 dark:hover:bg-emerald-900/40 transition-colors"
              >
                <Play className="w-3 h-3" />
                {t('page.index.install')}
              </button>
            </div>
          </div>

          <div className="bg-slate-50 dark:bg-slate-800/60 rounded-2xl p-4 max-h-64 overflow-y-auto">
            {loadingPipPackages ? (
              <div className="flex justify-center py-6">
                <RotateCw className="w-5 h-5 text-blue-500 animate-spin" />
              </div>
            ) : pipPackages.length === 0 ? (
              <p className="text-sm text-center text-slate-500 dark:text-slate-400">
                {t('page.index.no_packages')}
              </p>
            ) : (
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-xs text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                    <th className="text-left py-1.5">{t('page.index.pkg_name')}</th>
                    <th className="text-left py-1.5">{t('page.index.version')}</th>
                    <th className="text-right py-1.5">{t('page.index.actions')}</th>
                  </tr>
                </thead>
                <tbody>
                  {pipPackages.map((pkg) => (
                    <tr
                      key={pkg.name}
                      className="border-b border-slate-100 dark:border-slate-800/60 last:border-0"
                    >
                      <td className="py-2 text-slate-900 dark:text-white">{pkg.name}</td>
                      <td className="py-2 text-slate-600 dark:text-slate-400">{pkg.version}</td>
                      <td className="py-2 text-right">
                        <button
                          onClick={() => handleUninstallPip(pkg.name)}
                          disabled={uninstallingPip}
                          className="px-2.5 py-1 bg-rose-50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400 rounded-full text-xs font-semibold hover:bg-rose-100 dark:hover:bg-rose-900/40 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          {t('page.index.uninstall')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {pipOutputVisible && pipOutput.length > 0 && (
            <div className="bg-slate-950 rounded-2xl border border-slate-800 p-3 text-slate-100 font-mono space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-300">
                  {t('page.index.pip_output')}
                </span>
                <button
                  onClick={() => setPipOutputVisible(false)}
                  className="p-1 rounded-md text-slate-400 hover:text-slate-100 hover:bg-slate-800/80 transition-colors"
                  title={t('common.close')}
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
              <div className="text-xs max-h-48 overflow-y-auto space-y-0.5">
                {pipOutput.map((line, idx) => (
                  <div key={idx}>{line}</div>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      </div>

      </motion.div>

      {/* Install pip modal */}
      <AnimatePresence>
        {showInstallPipModal && (
          <motion.div
            className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              className="bg-white dark:bg-slate-900 rounded-3xl shadow-xl border border-slate-200 dark:border-slate-800 max-w-md w-full mx-4 p-6 space-y-4"
            >
              <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                {t('page.index.install_pip_title')}
              </h3>
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                  {t('page.index.pkg_name')}
                </label>
                <input
                  value={newPipPackage}
                  onChange={(e) => setNewPipPackage(e.target.value)}
                  placeholder={t('page.index.install_placeholder')}
                  className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/60"
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setShowInstallPipModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                >
                  {t('common.cancel')}
                </button>
                <button
                  onClick={handleInstallPip}
                  disabled={installingPip || !newPipPackage.trim()}
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-sm font-semibold text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {t('page.index.install')}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* RCON setup modal */}
      <AnimatePresence>
        {showRconSetupModal && (
          <motion.div
            className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              className="bg-white dark:bg-slate-900 rounded-3xl shadow-xl border border-slate-200 dark:border-slate-800 max-w-md w-full mx-4 p-6 space-y-4"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                  {t('page.mcdr.rcon.setup_modal_title')}
                </h3>
                <button
                  onClick={() => setShowRconSetupModal(false)}
                  className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {t('page.mcdr.rcon.setup_description')}
              </p>
              <div className="rounded-2xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 p-3 text-xs text-amber-800 dark:text-amber-300">
                {t('page.mcdr.rcon.setup_warning')}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowRconSetupModal(false)}
                  disabled={settingUpRcon}
                  className="flex-1 px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                >
                  {t('common.cancel')}
                </button>
                <button
                  onClick={setupRcon}
                  disabled={settingUpRcon}
                  className="flex-1 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-sm font-semibold text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                >
                  {settingUpRcon && <RotateCw className="w-4 h-4 animate-spin" />}
                  {settingUpRcon
                    ? t('page.mcdr.rcon.setting_up')
                    : t('page.mcdr.rcon.setup_confirm')}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Notification toast */}
      {showNotification && (
        <div
          className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-2xl shadow-lg flex items-center gap-2 text-sm ${
            notificationType === 'success'
              ? 'bg-emerald-500 text-white'
              : 'bg-rose-500 text-white'
          }`}
        >
          <Info className="w-4 h-4" />
          <span>{notificationMessage}</span>
          <button
            onClick={() => setShowNotification(false)}
            className="ml-2 text-white/80 hover:text-white"
          >
            ×
          </button>
        </div>
      )}
    </>
  )
}

export default Dashboard