import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { motion } from 'framer-motion'
import { Zap, User, Lock, Check, ArrowRight, Loader2, Sun, Moon, Languages, KeyRound } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import VersionFooter from '../components/VersionFooter'

const Login: React.FC = () => {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { login, loginWithTempCode, isAuthenticated } = useAuth()
  const { mode, setMode, label: themeLabel } = useTheme()
  const [loginMode, setLoginMode] = useState<'password' | 'tempCode'>('password')
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [tempCode, setTempCode] = useState('')
  const [remember, setRemember] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/index')
    }
  }, [isAuthenticated, navigate])

  const changeLanguage = (code: string) => {
    if (i18n.language === code) return
    i18n.changeLanguage(code)
    localStorage.setItem('language', code)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    let result
    if (loginMode === 'password') {
      result = await login(account, password, remember)
    } else {
      result = await loginWithTempCode(tempCode)
    }

    if (result.success) {
      navigate('/index')
    } else {
      setError(result.message || t('login.msg.login_failed'))
    }
    setLoading(false)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-4 transition-colors duration-300 relative overflow-hidden">
      {/* Theme & language toggles (top-right) */}
      <div className="absolute top-4 right-4 z-20 flex gap-2">
        {/* Theme */}
        <div className="relative group">
          <button
            className="flex items-center justify-center p-2 text-slate-500 hover:text-blue-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-blue-400 dark:hover:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 transition-colors"
            title={themeLabel}
          >
            {mode === 'dark' ? (
              <Moon className="w-4 h-4" />
            ) : mode === 'light' ? (
              <Sun className="w-4 h-4" />
            ) : (
              <div className="relative w-4 h-4">
                <Sun className="w-4 h-4 absolute inset-0 opacity-70" />
                <Moon className="w-3 h-3 absolute -bottom-0.5 -right-0.5 opacity-80" />
              </div>
            )}
          </button>
          <div className="absolute z-30 mt-2 right-0 w-32 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-lg opacity-0 scale-95 translate-y-1 group-hover:opacity-100 group-hover:scale-100 group-hover:translate-y-0 transition-all">
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

        {/* Language */}
        <div className="relative group">
          <button className="flex items-center justify-center gap-1.5 p-2 text-slate-500 hover:text-blue-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-blue-400 dark:hover:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 transition-colors">
            <Languages className="w-4 h-4" />
            <span className="text-xs font-bold">
              {i18n.language === 'zh-CN' ? t('nav.lang_short') : 'EN'}
            </span>
          </button>
          <div className="absolute z-30 mt-2 right-0 w-32 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-lg opacity-0 scale-95 translate-y-1 group-hover:opacity-100 group-hover:scale-100 group-hover:translate-y-0 transition-all">
            {[
              { code: 'zh-CN', label: t('lang.zh-CN') },
              { code: 'en-US', label: t('lang.en-US') },
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
      {/* Decorative background elements */}
      <motion.div 
        animate={{ 
          scale: [1, 1.2, 1],
          opacity: [0.1, 0.15, 0.1]
        }}
        transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
        className="absolute top-0 right-0 -mr-32 -mt-32 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl" 
      />
      <motion.div 
        animate={{ 
          scale: [1.2, 1, 1.2],
          opacity: [0.1, 0.15, 0.1]
        }}
        transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
        className="absolute bottom-0 left-0 -ml-32 -mb-32 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl" 
      />
      
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="max-w-md w-full relative z-10"
      >
        <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl p-8 rounded-[2rem] border border-slate-200 dark:border-slate-800 shadow-2xl space-y-8">
          <div className="text-center space-y-2">
            <motion.div 
              whileHover={{ rotate: 0, scale: 1.05 }}
              initial={{ rotate: 3 }}
              className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-2xl text-white shadow-xl shadow-blue-500/30 mb-4 transition-transform duration-300 cursor-pointer"
            >
              <Zap className="w-10 h-10 fill-current" />
            </motion.div>
            <h2 className="text-3xl font-black text-slate-900 dark:text-white tracking-tight">
              {t('app.name')}
            </h2>
            <p className="text-slate-500 dark:text-slate-400 font-medium">
              {t('app.desc')}
            </p>
          </div>

          <form className="space-y-6" onSubmit={handleSubmit}>
            {error && (
              <motion.div 
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                className="bg-rose-50 dark:bg-rose-900/20 border border-rose-100 dark:border-rose-900/30 text-rose-600 dark:text-rose-400 px-4 py-3 rounded-xl text-sm font-medium"
              >
                {error}
              </motion.div>
            )}

            {/* 登录模式切换 */}
            <div className="flex gap-2 p-1 bg-slate-100 dark:bg-slate-800 rounded-xl">
              <button
                type="button"
                onClick={() => {
                  setLoginMode('password')
                  setError('')
                }}
                className={`flex-1 py-2 px-4 rounded-lg text-sm font-semibold transition-all duration-200 ${
                  loginMode === 'password'
                    ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                {t('login.password_login')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setLoginMode('tempCode')
                  setError('')
                }}
                className={`flex-1 py-2 px-4 rounded-lg text-sm font-semibold transition-all duration-200 ${
                  loginMode === 'tempCode'
                    ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                {t('login.temp_code_login')}
              </button>
            </div>
            
            <div className="space-y-4">
              {loginMode === 'password' ? (
                <>
                  <div className="space-y-1.5">
                    <label htmlFor="account" className="block text-sm font-bold text-slate-700 dark:text-slate-300 ml-1">
                      {t('login.username')}
                    </label>
                    <div className="relative group">
                      <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400 group-focus-within:text-blue-500 transition-colors">
                        <User className="w-5 h-5" />
                      </div>
                      <input
                        id="account"
                        type="text"
                        required
                        autoComplete="username"
                        value={account}
                        onChange={(e) => setAccount(e.target.value)}
                        placeholder={t('login.placeholder_username')}
                        className="block w-full pl-11 pr-4 py-3 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-2xl text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200"
                      />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <label htmlFor="password" className="block text-sm font-bold text-slate-700 dark:text-slate-300 ml-1">
                      {t('login.password')}
                    </label>
                    <div className="relative group">
                      <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400 group-focus-within:text-blue-500 transition-colors">
                        <Lock className="w-5 h-5" />
                      </div>
                      <input
                        id="password"
                        type="password"
                        required
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder={t('login.placeholder_password')}
                        className="block w-full pl-11 pr-4 py-3 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-2xl text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200"
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-between px-1">
                    <label className="flex items-center group cursor-pointer">
                      <div className="relative flex items-center">
                        <input
                          type="checkbox"
                          checked={remember}
                          onChange={(e) => setRemember(e.target.checked)}
                          className="peer sr-only"
                        />
                        <div className="w-5 h-5 border-2 border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-800 peer-checked:bg-blue-600 peer-checked:border-blue-600 transition-all duration-200" />
                        <Check className="absolute w-3.5 h-3.5 text-white opacity-0 peer-checked:opacity-100 left-0.5.5 transition-opacity duration-200" style={{ left: '3px' }} />
                      </div>
                      <span className="ml-2.5 text-sm font-semibold text-slate-600 dark:text-slate-400 group-hover:text-slate-900 dark:group-hover:text-white transition-colors">
                        {t('login.remember')}
                      </span>
                    </label>
                  </div>
                </>
              ) : (
                <div className="space-y-1.5">
                  <label htmlFor="tempCode" className="block text-sm font-bold text-slate-700 dark:text-slate-300 ml-1">
                    {t('login.temp_code')}
                  </label>
                  <div className="relative group">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400 group-focus-within:text-blue-500 transition-colors">
                      <KeyRound className="w-5 h-5" />
                    </div>
                    <input
                      id="tempCode"
                      type="text"
                      required
                      value={tempCode}
                      onChange={(e) => setTempCode(e.target.value)}
                      placeholder={t('login.placeholder_temp_code')}
                      className="block w-full pl-11 pr-4 py-3 bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-2xl text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all duration-200"
                    />
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400 ml-1">
                    {t('login.temp_code_hint')}
                  </p>
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="group relative w-full flex justify-center py-3.5 px-4 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-2xl shadow-lg shadow-blue-500/30 transition-all duration-200 hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-50 disabled:cursor-not-allowed overflow-hidden"
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>{t('common.notice_loading')}</span>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <span>{t('login.login')}</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </div>
              )}
            </button>
          </form>
          
          <div className="pt-4 text-center border-t border-slate-100 dark:border-slate-800">
            <button
              onClick={() => navigate('/player-chat')}
              className="text-sm font-semibold text-slate-500 hover:text-blue-600 transition-colors"
            >
              {t('login.go_chat')}
            </button>
          </div>
        </div>
        
        <VersionFooter className="mt-8 text-center" />
      </motion.div>
    </div>
  )
}

export default Login