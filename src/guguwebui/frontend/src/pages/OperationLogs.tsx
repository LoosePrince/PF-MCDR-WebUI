import { AnimatePresence, motion } from 'framer-motion'
import { ClipboardList, RotateCw, X } from 'lucide-react'
import React, { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import api, { isCancel } from '../utils/api'

interface AuditAccount {
  username?: string | null
  nickname?: string | null
  auth_via?: string | null
}

interface AuditRecord {
  id?: string
  ts?: number
  operation_type?: string
  summary?: string
  detail?: unknown
  account?: AuditAccount | null
}

function formatAccount(a: AuditAccount | null | undefined, t: (k: string) => string): string {
  if (!a) return '—'
  const u = a.username ?? ''
  const n = a.nickname ?? ''
  if (a.auth_via === 'panel_token') {
    return n || u || t('page.operation_logs.panel_actor')
  }
  if (u && n) return `${u} (${n})`
  if (u) return u
  if (n) return n
  return '—'
}

const OperationLogs: React.FC = () => {
  const { t, i18n } = useTranslation()
  const [records, setRecords] = useState<AuditRecord[]>([])
  const [total, setTotal] = useState(0)
  const [nextOffset, setNextOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detailRecord, setDetailRecord] = useState<AuditRecord | null>(null)
  const limit = 50

  const load = useCallback(
    async (startOffset: number, append: boolean, signal?: AbortSignal) => {
      if (append) setLoadingMore(true)
      else setLoading(true)
      setError(null)
      try {
        const { data } = await api.get('/audit_logs', {
          params: { offset: startOffset, limit },
          signal,
        })
        if (data.status === 'success' && Array.isArray(data.records)) {
          setTotal(typeof data.total === 'number' ? data.total : 0)
          const rows = data.records as AuditRecord[]
          if (append) {
            setRecords((prev) => [...prev, ...rows])
          } else {
            setRecords(rows)
          }
          setNextOffset(startOffset + rows.length)
        } else {
          setError(t('page.operation_logs.load_failed'))
        }
      } catch (e: unknown) {
        const err = e as { name?: string; code?: string }
        if (isCancel(e) || err.name === 'AbortError' || err.code === 'ERR_CANCELED') {
          return
        }
        setError(t('page.operation_logs.load_failed'))
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [limit, t]
  )

  useEffect(() => {
    const ac = new AbortController()
    void load(0, false, ac.signal)
    return () => ac.abort()
  }, [load])

  const hasMore = nextOffset < total && records.length > 0

  const formatTime = (ts: number | undefined) => {
    if (ts == null || Number.isNaN(ts)) return '—'
    try {
      return new Date(ts * 1000).toLocaleString(i18n.language)
    } catch {
      return String(ts)
    }
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-6"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-violet-500 rounded-2xl text-white shadow-lg shadow-violet-500/25">
              <ClipboardList className="w-7 h-7" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                {t('page.operation_logs.title')}
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {t('page.operation_logs.subtitle')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void load(0, false)}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 text-sm font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 transition-colors"
          >
            <RotateCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            {t('common.refresh')}
          </button>
        </div>

        <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
          {loading && records.length === 0 ? (
            <div className="flex justify-center py-16 text-slate-500 dark:text-slate-400 gap-2">
              <RotateCw className="w-5 h-5 animate-spin" />
              {t('common.notice_loading')}
            </div>
          ) : error ? (
            <div className="p-8 text-center text-rose-600 dark:text-rose-400">{error}</div>
          ) : records.length === 0 ? (
            <div className="p-8 text-center text-slate-500 dark:text-slate-400">
              {t('page.operation_logs.empty')}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-800/40">
                    <th className="px-4 py-3 whitespace-nowrap">{t('page.operation_logs.col_time')}</th>
                    <th className="px-4 py-3 whitespace-nowrap">{t('page.operation_logs.col_account')}</th>
                    <th className="px-4 py-3 whitespace-nowrap">{t('page.operation_logs.col_operation')}</th>
                    <th className="px-4 py-3 min-w-[12rem]">{t('page.operation_logs.col_summary')}</th>
                    <th className="px-4 py-3 whitespace-nowrap text-right">{t('page.operation_logs.col_detail')}</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((row) => (
                    <tr
                      key={row.id || `${row.ts}-${row.summary}`}
                      className="border-b border-slate-100 dark:border-slate-800/80 last:border-0 hover:bg-slate-50/80 dark:hover:bg-slate-800/30"
                    >
                      <td className="px-4 py-3 text-slate-600 dark:text-slate-300 whitespace-nowrap tabular-nums">
                        {formatTime(row.ts)}
                      </td>
                      <td className="px-4 py-3 text-slate-900 dark:text-white whitespace-nowrap">
                        {formatAccount(row.account, t)}
                      </td>
                      <td className="px-4 py-3 text-slate-600 dark:text-slate-400 font-mono text-xs whitespace-nowrap">
                        {row.operation_type ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-slate-800 dark:text-slate-200 max-w-md break-words">
                        {row.summary ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => setDetailRecord(row)}
                          className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
                        >
                          {t('page.operation_logs.view_detail')}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {hasMore && !loading && (
            <div className="p-4 border-t border-slate-200 dark:border-slate-800 flex justify-center">
              <button
                type="button"
                disabled={loadingMore}
                onClick={() => void load(nextOffset, true)}
                className="px-5 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-100 text-sm font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 inline-flex items-center gap-2"
              >
                {loadingMore && <RotateCw className="w-4 h-4 animate-spin" />}
                {t('page.operation_logs.load_more')}
              </button>
            </div>
          )}
        </div>
      </motion.div>

      <AnimatePresence>
        {detailRecord && (
          <motion.div
            className="fixed inset-0 z-[60] bg-slate-900/60 flex items-center justify-center p-4"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setDetailRecord(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ duration: 0.15 }}
              className="bg-white dark:bg-slate-900 rounded-3xl shadow-xl border border-slate-200 dark:border-slate-800 max-w-3xl w-full max-h-[85vh] flex flex-col"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-800 shrink-0">
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                  {t('page.operation_logs.detail_title')}
                </h3>
                <button
                  type="button"
                  onClick={() => setDetailRecord(null)}
                  className="p-2 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                  aria-label={t('common.close')}
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <pre className="flex-1 min-h-0 overflow-auto px-5 py-4 text-xs font-mono text-slate-800 dark:text-slate-200 whitespace-pre-wrap break-words">
                {JSON.stringify(
                  {
                    id: detailRecord.id,
                    ts: detailRecord.ts,
                    operation_type: detailRecord.operation_type,
                    summary: detailRecord.summary,
                    account: detailRecord.account,
                    detail: detailRecord.detail,
                  },
                  null,
                  2
                )}
              </pre>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

export default OperationLogs
