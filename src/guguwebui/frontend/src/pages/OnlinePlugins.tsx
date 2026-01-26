import React from 'react'
import { useTranslation } from 'react-i18next'

const OnlinePlugins: React.FC = () => {
  const { t } = useTranslation()

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
        {t('nav.online_plugins')}
      </h1>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <p className="text-gray-600 dark:text-gray-400">在线插件页面（待实现）</p>
      </div>
    </div>
  )
}

export default OnlinePlugins
