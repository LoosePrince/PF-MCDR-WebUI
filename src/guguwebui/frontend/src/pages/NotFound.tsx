import React from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { motion } from 'framer-motion'
import { Home, AlertCircle } from 'lucide-react'

const NotFound: React.FC = () => {
  const { t } = useTranslation()

  return (
    <div className="min-h-[80vh] flex items-center justify-center">
      <motion.div 
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="text-center space-y-6"
      >
        <div className="relative inline-block">
          <motion.div
            animate={{ rotate: [0, -10, 10, -10, 10, 0] }}
            transition={{ duration: 2, repeat: Infinity, repeatDelay: 3 }}
          >
            <AlertCircle className="w-24 h-24 text-rose-500 mx-auto" />
          </motion.div>
          <h1 className="text-9xl font-black text-slate-200 dark:text-slate-800 absolute -z-10 top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
            404
          </h1>
        </div>
        
        <div className="space-y-2 relative z-10">
          <h2 className="text-3xl font-bold text-slate-900 dark:text-white">
            {t('page.404.title')}
          </h2>
          <p className="text-slate-500 dark:text-slate-400 max-w-md mx-auto">
            {t('page.404.description')}
          </p>
        </div>

        <motion.div
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <Link
            to="/index"
            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white font-bold rounded-2xl shadow-lg shadow-blue-500/30 hover:bg-blue-700 transition-colors"
          >
            <Home className="w-5 h-5" />
            {t('page.404.back_home')}
          </Link>
        </motion.div>
      </motion.div>
    </div>
  )
}

export default NotFound
