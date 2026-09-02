import { motion } from 'framer-motion'
import { X } from 'lucide-react'
import React, { useEffect } from 'react'
import { createPortal } from 'react-dom'

type ModalProps = {
  isOpen: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  fullWidth?: boolean
  closeLabel?: string
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  fullWidth = false,
  closeLabel = 'Close',
}) => {
  useEffect(() => {
    if (!isOpen) return undefined
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return createPortal(
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4" style={{ margin: 0 }}>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/60"
      />
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 20 }}
        onClick={(event) => event.stopPropagation()}
        className={`relative z-10 max-h-[90vh] w-full overflow-y-auto rounded-3xl border border-slate-200 bg-white p-8 shadow-2xl dark:border-slate-800 dark:bg-slate-900 ${fullWidth ? 'max-w-5xl' : 'max-w-lg'}`}
      >
        <div className="mb-6 flex items-center justify-between gap-3">
          <h3 className="truncate text-xl font-bold text-slate-900 dark:text-white">{title}</h3>
          <button type="button" onClick={onClose} title={closeLabel} aria-label={closeLabel} className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X size={24} />
          </button>
        </div>
        {children}
      </motion.div>
    </div>,
    document.body,
  )
}
