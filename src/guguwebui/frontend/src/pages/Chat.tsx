import React from 'react'
import { useTranslation } from 'react-i18next'

const Chat: React.FC = () => {
  const { t } = useTranslation()

  return (
    <div>
      <h1>
        {t('page.chat.header_title')}
      </h1>
      <p>
        {t('page.chat.room.desc')}
      </p>
    </div>
  )
}

export default Chat
