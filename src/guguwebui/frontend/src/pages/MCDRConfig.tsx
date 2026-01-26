import React from 'react'
import { useTranslation } from 'react-i18next'

const MCDRConfig: React.FC = () => {
  const { t } = useTranslation()

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
        {t('nav.mcdr_config')}
      </h1>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <p className="text-gray-600 dark:text-gray-400">MCDR 配置页面（待实现）</p>
      </div>
    </div>
  )
}

export default MCDRConfig
