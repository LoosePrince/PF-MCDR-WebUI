import { createContext, useContext } from 'react'

type NoticeModalContextValue = {
  openNoticeModal: () => void
}

const NoticeModalContext = createContext<NoticeModalContextValue | null>(null)

export function useNoticeModal(): NoticeModalContextValue | null {
  return useContext(NoticeModalContext)
}

export const NoticeModalProvider = NoticeModalContext.Provider
