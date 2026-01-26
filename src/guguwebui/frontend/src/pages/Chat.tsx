import React from 'react'
import { useTranslation } from 'react-i18next'

const Chat: React.FC = () => {
  const { t } = useTranslation()

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-4">
      <div className="max-w-4xl mx-auto bg-white dark:bg-gray-800 rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
          {t('page.chat.header_title')}
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          {t('page.chat.room.desc')}
        </p>
      </div>
    </div>
  )
}

export default Chat
