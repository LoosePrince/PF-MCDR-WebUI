import React, { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Network,
  Shield,
  Lock,
  User,
  Bot,
  Database,
  MessageSquare,
  Plug,
  Save,
  CheckCircle,
  Eye,
  EyeOff,
  Plus,
  Trash2,
  Info,
  Loader2,
  AlertCircle,
  X
} from 'lucide-react'
import axios from 'axios'

interface Repository {
  name: string
  url: string
}

interface WebConfig {
  host: string
  port: number
  super_admin_account: string | number
  disable_admin_login_web: boolean
  enable_temp_login_password: boolean
  ai_api_key_configured: boolean
  ai_model: string
  ai_api_url: string
  mcdr_plugins_url: string
  repositories: Repository[]
  ssl_enabled: boolean
  ssl_certfile: string
  ssl_keyfile: string
  ssl_keyfile_password?: string
  public_chat_enabled: boolean
  public_chat_to_game_enabled: boolean
  chat_verification_expire_minutes: number
  chat_session_expire_hours: number
  chat_message_count: number
}

const Settings: React.FC = () => {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [config, setConfig] = useState<WebConfig | null>(null)
  const [aiApiKey, setAiApiKey] = useState('')
  const [showAiKey, setShowAiKey] = useState(false)
  const [validatingAiKey, setValidatingAiKey] = useState(false)
  const [pimStatus, setPimStatus] = useState<'installed' | 'not_installed' | 'installing' | 'loading'>('loading')
  const [newRepo, setNewRepo] = useState<Repository>({ name: '', url: '' })

  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  const showNotification = useCallback((message: string, type: 'success' | 'error') => {
    setNotification({ message, type })
    setTimeout(() => setNotification(null), 5000)
  }, [])

  const fetchConfig = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/get_web_config')
      setConfig(data)
    } catch (error) {
      console.error('Failed to fetch config:', error)
      showNotification(t('page.settings.msg.get_config_failed'), 'error')
    } finally {
      setLoading(false)
    }
  }, [t, showNotification])

  const fetchPimStatus = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/check_pim_status')
      if (data.status === 'success') {
        setPimStatus(data.pim_status)
      } else {
        setPimStatus('not_installed')
        console.error('Failed to fetch PIM status:', data.message)
      }
    } catch (error) {
      console.error('Failed to fetch PIM status:', error)
      setPimStatus('not_installed')
    }
  }, [])

  useEffect(() => {
    fetchConfig()
    fetchPimStatus()
  }, [fetchConfig, fetchPimStatus])

  const handleSave = async (action: string, data: any) => {
    setSaving(action)
    try {
      const payload = { action, ...data }
      const { data: resp } = await axios.post('/api/save_web_config', payload)
      if (resp.status === 'success') {
        showNotification(resp.message || t('common.save_success'), 'success')
        fetchConfig()
      } else {
        showNotification(t('page.settings.msg.save_failed_prefix') + resp.message, 'error')
      }
    } catch (error: any) {
      console.error('Save failed:', error)
      showNotification(t('page.settings.msg.save_error_prefix') + error.message, 'error')
    } finally {
      setSaving(null)
    }
  }

  const toggleSetting = async (key: 'disable_admin_login_web' | 'enable_temp_login_password') => {
    setSaving(key)
    try {
      const { data: resp } = await axios.post('/api/save_web_config', { action: key })
      if (resp.status === 'success') {
        showNotification(resp.message ? t('page.settings.msg.toggle_enabled') : t('page.settings.msg.toggle_disabled'), 'success')
        fetchConfig()
      } else {
        showNotification(t('page.settings.msg.toggle_failed_prefix') + resp.message, 'error')
      }
    } catch (error: any) {
      showNotification(t('page.settings.msg.toggle_error_prefix') + error.message, 'error')
    } finally {
      setSaving(null)
    }
  }

  const validateAiKey = async () => {
    if (!aiApiKey) {
      showNotification(t('page.settings.msg.api_key_required'), 'error')
      return
    }
    setValidatingAiKey(true)
    try {
      const { data } = await axios.post('/api/deepseek', {
        query: '测试密钥是否有效，请回复"有效"',
        system_prompt: '你是一个简单的验证程序，只需回复"有效"',
        api_key: aiApiKey,
        api_url: config?.ai_api_url,
        model: config?.ai_model
      })
      if (data.status === 'success') {
        showNotification(t('page.settings.msg.api_key_validate_success'), 'success')
      } else {
        showNotification(t('page.settings.msg.api_key_validate_failed_prefix') + (data.message || ''), 'error')
      }
    } catch (error: any) {
      showNotification(t('page.settings.msg.api_key_validate_error_prefix') + error.message, 'error')
    } finally {
      setValidatingAiKey(false)
    }
  }

  const addRepository = () => {
    if (!newRepo.name || !newRepo.url) {
      showNotification(t('page.settings.msg.repo_name_url_required'), 'error')
      return
    }
    if (config) {
      const updatedRepos = [...config.repositories, newRepo]
      setConfig({ ...config, repositories: updatedRepos })
      setNewRepo({ name: '', url: '' })
      showNotification(t('page.settings.msg.repo_added_tip'), 'success')
    }
  }

  const deleteRepository = (index: number) => {
    if (config) {
      const updatedRepos = config.repositories.filter((_, i) => i !== index)
      setConfig({ ...config, repositories: updatedRepos })
      showNotification(t('page.settings.msg.repo_deleted_tip'), 'success')
    }
  }

  const installPim = async () => {
    setPimStatus('installing')
    try {
      const { data } = await axios.get('/api/install_pim_plugin')
      if (data.status === 'success') {
        showNotification(t('page.settings.msg.pim_install_success'), 'success')
        setPimStatus('installed')
      } else {
        showNotification(t('page.settings.msg.pim_install_failed_prefix') + (data.message || ''), 'error')
        setPimStatus('not_installed')
      }
    } catch (error: any) {
      showNotification(t('page.settings.msg.pim_install_error_prefix') + error.message, 'error')
      setPimStatus('not_installed')
    }
  }

  if (loading || !config) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.1 }
    }
  }

  const itemVariants = {
    hidden: { y: 20, opacity: 0 },
    visible: { y: 0, opacity: 1 }
  }

  return (
    <div className="space-y-8 pb-12">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col gap-2"
      >
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white">
          {t('page.settings.header')}
        </h1>
        <p className="text-slate-500 dark:text-slate-400">
          {t('page.settings.network.tip')}
        </p>
      </motion.div>

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-1 lg:grid-cols-2 gap-6"
      >
        {/* Network & Account Section */}
        <div className="space-y-6">
          {/* Network Settings */}
          <motion.div variants={itemVariants} className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
            <div className="flex items-center gap-3 text-blue-500">
              <Network className="w-6 h-6" />
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                {t('page.settings.network.title')}
              </h2>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                  {t('page.settings.network.host')}
                </label>
                <input
                  type="text"
                  value={config.host}
                  onChange={(e) => setConfig({ ...config, host: e.target.value })}
                  placeholder="127.0.0.1"
                  className="w-full px-4 py-2.5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500/60 transition-all outline-none"
                />
                <p className="text-xs text-slate-500">{t('page.settings.network.host_hint')}</p>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                  {t('page.settings.network.port')}
                </label>
                <input
                  type="number"
                  value={config.port}
                  onChange={(e) => setConfig({ ...config, port: parseInt(e.target.value) || 0 })}
                  placeholder="8000"
                  className="w-full px-4 py-2.5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500/60 transition-all outline-none"
                />
                <p className="text-xs text-slate-500">{t('page.settings.network.port_hint')}</p>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() =>
                  handleSave('config', {
                    host: config.host,
                    port: String(config.port)
                  })
                }
                disabled={saving === 'config'}
                className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold rounded-2xl transition-all shadow-lg shadow-blue-500/20"
              >
                {saving === 'config' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {t('page.settings.network.save')}
              </button>
            </div>
          </motion.div>

          {/* Account Settings */}
          <motion.div variants={itemVariants} className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
            <div className="flex items-center gap-3 text-purple-500">
              <User className="w-6 h-6" />
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                {t('page.settings.account.title')}
              </h2>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                {t('page.settings.account.super_admin')}
              </label>
              <input
                type="text"
                value={config.super_admin_account}
                onChange={(e) => setConfig({ ...config, super_admin_account: e.target.value })}
                className="w-full px-4 py-2.5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-purple-500/60 transition-all outline-none"
              />
              <p className="text-xs text-slate-500">{t('page.settings.account.super_admin_hint')}</p>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() =>
                  handleSave('config', {
                    superaccount: String(config.super_admin_account)
                  })
                }
                disabled={saving === 'account'}
                className="flex items-center gap-2 px-6 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-semibold rounded-2xl transition-all shadow-lg shadow-purple-500/20"
              >
                {saving === 'account' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {t('page.settings.account.save')}
              </button>
            </div>
          </motion.div>

          {/* Security Settings */}
          <motion.div variants={itemVariants} className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
            <div className="flex items-center gap-3 text-rose-500">
              <Lock className="w-6 h-6" />
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                {t('page.settings.security.title')}
              </h2>
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800/60 rounded-2xl">
                <div>
                  <p className="font-bold text-slate-900 dark:text-white">{t('page.settings.security.disable_admin_web')}</p>
                </div>
                <button
                  onClick={() => toggleSetting('disable_admin_login_web')}
                  className={`w-12 h-6 rounded-full p-1 transition-colors ${config.disable_admin_login_web ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'}`}
                >
                  <motion.div
                    animate={{ x: config.disable_admin_login_web ? 24 : 0 }}
                    className="w-4 h-4 bg-white rounded-full shadow-sm"
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800/60 rounded-2xl">
                <div>
                  <p className="font-bold text-slate-900 dark:text-white">{t('page.settings.security.enable_temp_code')}</p>
                </div>
                <button
                  onClick={() => toggleSetting('enable_temp_login_password')}
                  className={`w-12 h-6 rounded-full p-1 transition-colors ${config.enable_temp_login_password ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'}`}
                >
                  <motion.div
                    animate={{ x: config.enable_temp_login_password ? 24 : 0 }}
                    className="w-4 h-4 bg-white rounded-full shadow-sm"
                  />
                </button>
              </div>
            </div>
          </motion.div>
        </div>

        {/* SSL & AI Section */}
        <div className="space-y-6">
          {/* HTTPS Settings */}
          <motion.div variants={itemVariants} className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
            <div className="flex items-center gap-3 text-emerald-500">
              <Shield className="w-6 h-6" />
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                {t('page.settings.https.title')}
              </h2>
            </div>

            <div className="p-4 bg-blue-50 dark:bg-blue-900/10 border border-blue-100 dark:border-blue-900/20 rounded-2xl flex gap-3">
              <Info className="w-5 h-5 text-blue-500 shrink-0" />
              <div className="text-xs text-blue-700 dark:text-blue-300 space-y-1">
                <p className="font-bold">{t('page.settings.https.ssl_tip_title')}</p>
                <ul className="list-disc pl-4 space-y-1">
                  <li>{t('page.settings.https.ssl_tip_1')}</li>
                  <li>{t('page.settings.https.ssl_tip_4')}</li>
                </ul>
              </div>
            </div>

            <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800/60 rounded-2xl">
              <p className="font-bold text-slate-900 dark:text-white">{t('page.settings.https.enable')}</p>
              <button
                onClick={() => setConfig({ ...config, ssl_enabled: !config.ssl_enabled })}
                className={`w-12 h-6 rounded-full p-1 transition-colors ${config.ssl_enabled ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'}`}
              >
                <motion.div
                  animate={{ x: config.ssl_enabled ? 24 : 0 }}
                  className="w-4 h-4 bg-white rounded-full shadow-sm"
                />
              </button>
            </div>

            <AnimatePresence>
              {config.ssl_enabled && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="space-y-4 overflow-hidden"
                >
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('page.settings.https.cert')}</label>
                    <input
                      type="text"
                      value={config.ssl_certfile}
                      onChange={(e) => setConfig({ ...config, ssl_certfile: e.target.value })}
                      placeholder="./ssl/cert.pem"
                      className="w-full px-4 py-2.5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-emerald-500/60 transition-all outline-none"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('page.settings.https.key')}</label>
                    <input
                      type="text"
                      value={config.ssl_keyfile}
                      onChange={(e) => setConfig({ ...config, ssl_keyfile: e.target.value })}
                      placeholder="./ssl/key.pem"
                      className="w-full px-4 py-2.5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-emerald-500/60 transition-all outline-none"
                    />
                  </div>
                  <form
                    className="space-y-2"
                    onSubmit={(e) => {
                      e.preventDefault()
                    }}
                  >
                    {/* 隐藏用户名字段以满足浏览器对密码表单的可访问性要求 */}
                    <input
                      type="text"
                      autoComplete="username"
                      tabIndex={-1}
                      aria-hidden="true"
                      className="hidden"
                    />
                    <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('page.settings.https.key_pass')}</label>
                    <input
                      type="password"
                      value={config.ssl_keyfile_password || ''}
                      onChange={(e) => setConfig({ ...config, ssl_keyfile_password: e.target.value })}
                      placeholder={t('page.settings.https.placeholder_key_pass')}
                      autoComplete="new-password"
                      className="w-full px-4 py-2.5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-emerald-500/60 transition-all outline-none"
                    />
                  </form>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => handleSave('config', {
                  ssl_enabled: config.ssl_enabled,
                  ssl_certfile: config.ssl_certfile,
                  ssl_keyfile: config.ssl_keyfile,
                  ssl_keyfile_password: config.ssl_keyfile_password
                })}
                disabled={saving === 'ssl'}
                className="flex items-center gap-2 px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-semibold rounded-2xl transition-all shadow-lg shadow-emerald-500/20"
              >
                {saving === 'ssl' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {t('page.settings.https.save')}
              </button>
            </div>
          </motion.div>

          {/* AI Settings */}
          <motion.div variants={itemVariants} className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
            <div className="flex items-center gap-3 text-amber-500">
              <Bot className="w-6 h-6" />
              <h2 className="text-xl font-bold text-slate-900 dark:text-white">
                {t('page.settings.ai.title')}
              </h2>
            </div>

            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('page.settings.ai.api_url')}</label>
                <input
                  type="text"
                  value={config.ai_api_url}
                  onChange={(e) => setConfig({ ...config, ai_api_url: e.target.value })}
                  placeholder="https://api.deepseek.com/chat/completions"
                  className="w-full px-4 py-2.5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-amber-500/60 transition-all outline-none"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('page.settings.ai.model')}</label>
                <input
                  type="text"
                  value={config.ai_model}
                  onChange={(e) => setConfig({ ...config, ai_model: e.target.value })}
                  placeholder="deepseek-chat"
                  className="w-full px-4 py-2.5 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-amber-500/60 transition-all outline-none"
                />
              </div>
              <form
                className="space-y-2"
                onSubmit={(e) => {
                  e.preventDefault()
                }}
              >
                {/* 隐藏用户名字段以满足浏览器对密码表单的可访问性要求 */}
                <input
                  type="text"
                  autoComplete="username"
                  tabIndex={-1}
                  aria-hidden="true"
                  className="hidden"
                />
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('page.settings.ai.api_key')}</label>
                <div className="relative">
                  <input
                    type={showAiKey ? 'text' : 'password'}
                    value={aiApiKey}
                    onChange={(e) => setAiApiKey(e.target.value)}
                    placeholder={config.ai_api_key_configured ? '••••••••••••••••' : t('page.settings.ai.placeholder_api_key')}
                    autoComplete="new-password"
                    className="w-full px-4 py-2.5 pr-12 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:ring-2 focus:ring-amber-500/60 transition-all outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowAiKey(!showAiKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    {showAiKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
                <div className="flex justify-end gap-2 mt-2">
                  <button
                    type="button"
                    onClick={validateAiKey}
                    disabled={validatingAiKey || !aiApiKey}
                    className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 text-sm font-medium rounded-xl transition-all"
                  >
                    {validatingAiKey ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                    {t('page.settings.ai.validate')}
                  </button>
                </div>
              </form>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => handleSave('config', { ai_api_key: aiApiKey || undefined, ai_api_url: config.ai_api_url, ai_model: config.ai_model })}
                disabled={saving === 'ai'}
                className="flex items-center gap-2 px-6 py-2.5 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white font-semibold rounded-2xl transition-all shadow-lg shadow-amber-500/20"
              >
                {saving === 'ai' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {t('page.settings.ai.save')}
              </button>
            </div>
          </motion.div>
        </div>

        {/* Repositories Section */}
        <motion.div variants={itemVariants} className="lg:col-span-2 bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div className="flex items-center gap-3 text-cyan-500">
            <Database className="w-6 h-6" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              {t('page.settings.repo.title')}
            </h2>
          </div>

          <p className="text-sm text-slate-500">{t('page.settings.repo.tip')}</p>

          <div className="overflow-x-auto rounded-2xl border border-slate-200 dark:border-slate-800">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 font-medium">
                <tr>
                  <th className="px-6 py-4">{t('page.settings.repo.name')}</th>
                  <th className="px-6 py-4">{t('page.settings.repo.url')}</th>
                  <th className="px-6 py-4 text-right">{t('page.settings.repo.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {/* Official */}
                <tr className="bg-blue-50/30 dark:bg-blue-900/10">
                  <td className="px-6 py-4 font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-blue-500" />
                    {t('page.settings.repo.official')}
                  </td>
                  <td className="px-6 py-4 text-slate-500 truncate max-w-xs">{config.mcdr_plugins_url}</td>
                  <td className="px-6 py-4 text-right">
                    <span className="text-xs font-medium text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-full">
                      {t('page.settings.repo.default')}
                    </span>
                  </td>
                </tr>
                {/* Loose Repository (Hardcoded in old HTML, but maybe should be editable?) */}
                <tr className="bg-blue-50/30 dark:bg-blue-900/10">
                  <td className="px-6 py-4 font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-blue-500" />
                    {t('page.settings.repo.loose_repo')}
                  </td>
                  <td className="px-6 py-4 text-slate-500 truncate max-w-xs">https://looseprince.github.io/Plugin-Catalogue/plugins.json</td>
                  <td className="px-6 py-4 text-right">
                    <span className="text-xs font-medium text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-full">
                      {t('page.settings.repo.default')}
                    </span>
                  </td>
                </tr>
                {/* Custom Repos */}
                {config.repositories.map((repo, idx) => (
                  <tr key={idx}>
                    <td className="px-6 py-4 text-slate-900 dark:text-white font-medium">{repo.name}</td>
                    <td className="px-6 py-4 text-slate-500 truncate max-w-xs">{repo.url}</td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => deleteRepository(idx)}
                        className="p-2 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/20 rounded-xl transition-all"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                {/* Add New */}
                <tr className="bg-slate-50/30 dark:bg-slate-800/30">
                  <td className="px-6 py-3">
                    <input
                      value={newRepo.name}
                      onChange={(e) => setNewRepo({ ...newRepo, name: e.target.value })}
                      placeholder={t('page.settings.repo.placeholder_name')}
                      className="w-full px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs"
                    />
                  </td>
                  <td className="px-6 py-3">
                    <input
                      value={newRepo.url}
                      onChange={(e) => setNewRepo({ ...newRepo, url: e.target.value })}
                      placeholder={t('page.settings.repo.placeholder_url')}
                      className="w-full px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs"
                    />
                  </td>
                  <td className="px-6 py-3 text-right">
                    <button
                      onClick={addRepository}
                      className="p-2 bg-blue-600 text-white rounded-xl hover:bg-blue-700 shadow-sm"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="flex justify-end pt-2">
            <button
              onClick={() => handleSave('config', { repositories: config.repositories })}
              disabled={saving === 'repos'}
              className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold rounded-2xl transition-all shadow-lg shadow-blue-500/20"
            >
              {saving === 'repos' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {t('page.settings.repo.save')}
            </button>
          </div>
        </motion.div>

        {/* Public Chat Section */}
        <motion.div variants={itemVariants} className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div className="flex items-center gap-3 text-sky-500">
            <MessageSquare className="w-6 h-6" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              {t('page.settings.public_chat.title')}
            </h2>
          </div>

          <div className="p-4 bg-sky-50 dark:bg-sky-900/10 border border-sky-100 dark:border-sky-900/20 rounded-2xl flex gap-3">
            <Info className="w-5 h-5 text-sky-500 shrink-0" />
            <p className="text-xs text-sky-700 dark:text-sky-300">{t('page.settings.public_chat.tip')}</p>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800/60 rounded-2xl">
              <div>
                <p className="font-bold text-slate-900 dark:text-white">{t('page.settings.public_chat.enable')}</p>
                <p className="text-xs text-slate-500">{t('page.settings.public_chat.enable_desc')}</p>
              </div>
              <button
                onClick={() => setConfig({ ...config, public_chat_enabled: !config.public_chat_enabled })}
                className={`w-12 h-6 rounded-full p-1 transition-colors ${config.public_chat_enabled ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'}`}
              >
                <motion.div
                  animate={{ x: config.public_chat_enabled ? 24 : 0 }}
                  className="w-4 h-4 bg-white rounded-full shadow-sm"
                />
              </button>
            </div>

            <div className={`flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800/60 rounded-2xl transition-opacity ${!config.public_chat_enabled ? 'opacity-50' : 'opacity-100'}`}>
              <div>
                <p className="font-bold text-slate-900 dark:text-white">{t('page.settings.public_chat.enable_to_game')}</p>
                <p className="text-xs text-slate-500">{t('page.settings.public_chat.enable_to_game_desc')}</p>
              </div>
              <button
                disabled={!config.public_chat_enabled}
                onClick={() => setConfig({ ...config, public_chat_to_game_enabled: !config.public_chat_to_game_enabled })}
                className={`w-12 h-6 rounded-full p-1 transition-colors ${config.public_chat_to_game_enabled ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'}`}
              >
                <motion.div
                  animate={{ x: config.public_chat_to_game_enabled ? 24 : 0 }}
                  className="w-4 h-4 bg-white rounded-full shadow-sm"
                />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('page.settings.public_chat.verification_expire.title')}</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={config.chat_verification_expire_minutes}
                    onChange={(e) => setConfig({ ...config, chat_verification_expire_minutes: parseInt(e.target.value) || 0 })}
                    className="w-20 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm outline-none"
                  />
                  <span className="text-xs text-slate-500">{t('page.settings.public_chat.verification_expire.unit_min')}</span>
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('page.settings.public_chat.session_expire.title')}</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={config.chat_session_expire_hours}
                    onChange={(e) => setConfig({ ...config, chat_session_expire_hours: parseInt(e.target.value) || 0 })}
                    className="w-20 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm outline-none"
                  />
                  <span className="text-xs text-slate-500">{t('page.settings.public_chat.session_expire.unit_hour')}</span>
                </div>
              </div>
            </div>

            <div className="p-4 bg-rose-50 dark:bg-rose-900/10 border border-rose-100 dark:border-rose-900/20 rounded-2xl">
              <p className="font-bold text-rose-900 dark:text-rose-300 text-sm mb-2">{t('page.settings.public_chat.history.title')}</p>
              <div className="flex items-center justify-between">
                <div className="text-xs text-rose-700 dark:text-rose-400">
                  {t('page.settings.public_chat.history.count_prefix')}{config.chat_message_count}{t('page.settings.public_chat.history.count_suffix')}
                </div>
                <button
                  onClick={async () => {
                    if (confirm(t('page.settings.public_chat.history.clear') + '?')) {
                      await axios.post('/api/chat/clear_messages')
                      fetchConfig()
                    }
                  }}
                  className="flex items-center gap-2 px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl shadow-lg shadow-rose-500/20 transition-all"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  {t('page.settings.public_chat.history.clear')}
                </button>
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              onClick={() => handleSave('config', {
                public_chat_enabled: config.public_chat_enabled,
                public_chat_to_game_enabled: config.public_chat_to_game_enabled,
                chat_verification_expire_minutes: config.chat_verification_expire_minutes,
                chat_session_expire_hours: config.chat_session_expire_hours,
                chat_message_count: config.chat_message_count
              })}
              disabled={saving === 'chat'}
              className="flex items-center gap-2 px-6 py-2.5 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white font-semibold rounded-2xl transition-all shadow-lg shadow-sky-500/20"
            >
              {saving === 'chat' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {t('page.settings.public_chat.save')}
            </button>
          </div>
        </motion.div>

        {/* PIM Section */}
        <motion.div variants={itemVariants} className="bg-white dark:bg-slate-900 p-6 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm space-y-4">
          <div className="flex items-center gap-3 text-indigo-500">
            <Plug className="w-6 h-6" />
            <h2 className="text-xl font-bold text-slate-900 dark:text-white">
              {t('page.settings.pim.title')}
            </h2>
          </div>

          <div className="p-4 bg-indigo-50 dark:bg-indigo-900/10 border border-indigo-100 dark:border-indigo-900/20 rounded-2xl">
            <p className="text-xs text-indigo-700 dark:text-indigo-300 leading-relaxed">
              {t('page.settings.pim.desc')}
            </p>
          </div>

          <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800/60 rounded-2xl">
            <div className="flex items-center gap-2">
              <p className="font-bold text-slate-900 dark:text-white">{t('page.settings.pim.install_title')}</p>
              {pimStatus === 'installed' && <CheckCircle className="w-4 h-4 text-emerald-500" />}
            </div>

            <button
              disabled={pimStatus === 'installed' || pimStatus === 'installing'}
              onClick={installPim}
              className={`flex items-center gap-2 px-6 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold rounded-2xl transition-all shadow-lg shadow-indigo-500/20`}
            >
              {pimStatus === 'installing' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
              {pimStatus === 'installed' ? t('common.installed') : t('common.install')}
            </button>
          </div>

          {pimStatus === 'installed' && (
            <div className="p-4 bg-emerald-50 dark:bg-emerald-900/10 border border-emerald-100 dark:border-emerald-900/20 rounded-2xl flex gap-3">
              <CheckCircle className="w-5 h-5 text-emerald-500 shrink-0" />
              <p className="text-xs text-emerald-700 dark:text-emerald-300">{t('page.settings.pim.installed_tip')}</p>
            </div>
          )}
        </motion.div>
      </motion.div>

      {/* Notifications */}
      <AnimatePresence>
        {notification && (
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.9 }}
            className={`fixed bottom-8 right-8 z-50 flex items-center gap-3 px-6 py-4 rounded-3xl shadow-2xl border ${notification.type === 'success'
              ? 'bg-emerald-500 border-emerald-400 text-white'
              : 'bg-rose-500 border-rose-400 text-white'
              }`}
          >
            {notification.type === 'success' ? <CheckCircle className="w-6 h-6" /> : <AlertCircle className="w-6 h-6" />}
            <span className="font-bold">{notification.message}</span>
            <button onClick={() => setNotification(null)} className="ml-4 p-1 hover:bg-white/20 rounded-full transition-colors">
              <X className="w-4 h-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default Settings
