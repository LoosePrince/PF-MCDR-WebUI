import { motion } from 'framer-motion'
import { Activity } from 'lucide-react'
import React from 'react'
import { useTranslation } from 'react-i18next'
import ServerStatusDetail from '../components/ServerStatusDetail'

const ServerStatus: React.FC = () => {
  const { t } = useTranslation()
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      <div className="flex items-center gap-3">
        <div className="p-3 bg-cyan-500 rounded-2xl text-white shadow-lg shadow-cyan-500/25">
          <Activity className="w-7 h-7" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            {t('page.status.title')}
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {t('page.status.desc')}
          </p>
        </div>
      </div>
      <ServerStatusDetail />
    </motion.div>
  )
}

export default ServerStatus