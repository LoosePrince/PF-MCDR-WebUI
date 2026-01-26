import React from 'react'
import { useTranslation } from 'react-i18next'

const Terminal: React.FC = () => {
  const { t } = useTranslation()

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
        {t('nav.terminal')}
      </h1>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <p className="text-gray-600 dark:text-gray-400">终端日志页面（待实现）</p>
      </div>
    </div>
  )
}

export default Terminal
