import { AnimatePresence, motion } from 'framer-motion'
import {
  Ban,
  Bot,
  LayoutGrid,
  ListChecks,
  Plus,
  RotateCw,
  Search,
  Shield,
  ShieldCheck,
  ShieldOff,
  Undo2,
  Users,
  UserX,
  X
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import React, { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { NiceSelect } from '../components/NiceSelect'
import { Skeleton, TableRowSkeleton } from '../components/Skeleton'
import api, { isCancel } from '../utils/api'

type TabKey = 'all' | 'players' | 'bots' | 'whitelist' | 'ops' | 'bans'

interface PlayerRow {
  name: string
  uuid?: string | null
  uuid_only?: boolean
  online: boolean
  is_bot: boolean
  ips: string[]
  ip?: string | null
  session_seconds?: number | null
  total_playtime?: number | null
  last_seen?: number | null
  position?: { x: number; y: number; z: number } | null
  dimension?: string | null
  is_op: boolean
  whitelisted: boolean
  banned: boolean
}

interface WhitelistMember {
  name: string
  uuid: string
}

interface WhitelistData {
  enabled: boolean
  members: WhitelistMember[]
  server_running: boolean
}

interface OpEntry {
  name: string
  uuid: string
  level?: number | null
  bypassesPlayerLimit?: boolean
}

interface OpsData {
  ops: OpEntry[]
  server_running: boolean
}

interface BanEntry {
  uuid?: string
  name?: string
  ip?: string
  reason?: string
  created?: string
  expires?: string
  source?: string
}

interface BansData {
  players: BanEntry[]
  ips: BanEntry[]
  server_running: boolean
}

const TABS: { key: TabKey; labelKey: string; icon: LucideIcon }[] = [
  { key: 'all', labelKey: 'page.players.tabs.all', icon: LayoutGrid },
  { key: 'players', labelKey: 'page.players.tabs.players', icon: Users },
  { key: 'bots', labelKey: 'page.players.tabs.bots', icon: Bot },
  { key: 'whitelist', labelKey: 'page.players.tabs.whitelist', icon: ListChecks },
  { key: 'ops', labelKey: 'page.players.tabs.ops', icon: Shield },
  { key: 'bans', labelKey: 'page.players.tabs.bans', icon: Ban },
]

const ActionBtn: React.FC<{
  title: string
  loading?: boolean
  disabled?: boolean
  onClick: () => void
  tone?: 'default' | 'green' | 'amber' | 'rose' | 'blue'
  children: React.ReactNode
}> = ({ title, loading, disabled, onClick, tone = 'default', children }) => {
  const tones = {
    default:
      'text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-slate-100 dark:hover:bg-slate-700',
    green: 'text-green-600 hover:bg-green-50 dark:text-green-400 dark:hover:bg-green-900/20',
    amber: 'text-amber-600 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-900/20',
    rose: 'text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-900/20',
    blue: 'text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-900/20',
  }
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      disabled={disabled || loading}
      onClick={onClick}
      className={`p-1.5 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${tones[tone]}`}
    >
      {loading ? <RotateCw className="w-4 h-4 animate-spin" /> : children}
    </button>
  )
}

const badgeClass = (tone: 'green' | 'amber' | 'blue' | 'rose' | 'slate') => {
  const map = {
    green: 'bg-green-50 text-green-600 border-green-100 dark:bg-green-900/20 dark:text-green-400 dark:border-green-900/30',
    amber: 'bg-amber-50 text-amber-600 border-amber-100 dark:bg-amber-900/20 dark:text-amber-400 dark:border-amber-900/30',
    blue: 'bg-blue-50 text-blue-600 border-blue-100 dark:bg-blue-900/20 dark:text-blue-400 dark:border-blue-900/30',
    rose: 'bg-rose-50 text-rose-600 border-rose-100 dark:bg-rose-900/20 dark:text-rose-400 dark:border-rose-900/30',
    slate: 'bg-slate-50 text-slate-500 border-slate-200 dark:bg-slate-900/20 dark:text-slate-400 dark:border-slate-800',
  }
  return map[tone]
}

const shortUuid = (uuid?: string | null) => (uuid ? `${uuid.slice(0, 8)}…` : '—')

const TAB_VALUES: TabKey[] = ['all', 'players', 'bots', 'whitelist', 'ops', 'bans']
const FILTER_VALUES = ['all', 'online', 'offline', 'bot', 'op']

const Players: React.FC = () => {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()

  // tab / filter 与 URL 查询参数同步（?tab=players&filter=online）
  const tabParam = searchParams.get('tab')
  const tab: TabKey = TAB_VALUES.includes(tabParam as TabKey) ? (tabParam as TabKey) : 'players'
  const filterParam = searchParams.get('filter')
  const rawFilter = filterParam && FILTER_VALUES.includes(filterParam) ? filterParam : 'all'
  // 玩家页不含假人：玩家页上的 bot 子筛选视为全部
  const filter = tab === 'players' && rawFilter === 'bot' ? 'all' : rawFilter

  const setTab = useCallback(
    (next: TabKey) => {
      setSearchParams(
        (prev) => {
          const sp = new URLSearchParams(prev)
          if (next === 'players') sp.delete('tab')
          else sp.set('tab', next)
          // 玩家页不含假人：进入时清除 bot 子筛选
          if (next === 'players' && sp.get('filter') === 'bot') sp.delete('filter')
          return sp
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )

  const setFilter = useCallback(
    (next: string) => {
      setSearchParams(
        (prev) => {
          const sp = new URLSearchParams(prev)
          if (next === 'all') sp.delete('filter')
          else sp.set('filter', next)
          return sp
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )

  // 玩家列表
  const [search, setSearch] = useState('')
  const [players, setPlayers] = useState<PlayerRow[]>([])
  const [total, setTotal] = useState(0)
  const [onlineCount, setOnlineCount] = useState(0)
  const [botCount, setBotCount] = useState(0)
  const [nextOffset, setNextOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [serverRunning, setServerRunning] = useState(true)

  // 假人列表
  const [bots, setBots] = useState<PlayerRow[]>([])
  const [botsLoading, setBotsLoading] = useState(false)

  // 白名单 / OP / 封禁
  const [whitelist, setWhitelist] = useState<WhitelistData | null>(null)
  const [whitelistLoading, setWhitelistLoading] = useState(false)
  const [ops, setOps] = useState<OpsData | null>(null)
  const [opsLoading, setOpsLoading] = useState(false)
  const [bans, setBans] = useState<BansData | null>(null)
  const [bansLoading, setBansLoading] = useState(false)

  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; msg: string } | null>(null)

  // 弹窗
  const [banModal, setBanModal] = useState<{ name: string; ip: string | null } | null>(null)
  const [unbanModal, setUnbanModal] = useState<{ type: 'player' | 'ip'; target: string } | null>(null)
  const [kickModal, setKickModal] = useState<{ name: string } | null>(null)

  // 白名单 / OP 添加输入
  const [newMember, setNewMember] = useState('')
  const [newOpName, setNewOpName] = useState('')
  const [banForm, setBanForm] = useState({ type: 'player', target: '', reason: '' })

  const showNotice = useCallback((msg: string, type: 'success' | 'error' = 'success') => {
    setNotice({ type, msg })
    window.setTimeout(() => setNotice(null), 4000)
  }, [])

  const fetchPlayers = useCallback(
    async (offset: number, append: boolean) => {
      if (append) setLoadingMore(true)
      else setLoading(true)
      try {
        const { data } = await api.get('/players', {
          params: { search, filter, offset, limit: 50, exclude_bots: tab === 'players' },
        })
        if (data.status === 'success' && Array.isArray(data.players)) {
          setServerRunning(!!data.server_running)
          setTotal(typeof data.total === 'number' ? data.total : 0)
          setOnlineCount(typeof data.online_count === 'number' ? data.online_count : 0)
          setBotCount(typeof data.bot_count === 'number' ? data.bot_count : 0)
          const rows = data.players as PlayerRow[]
          setPlayers((prev) => (append ? [...prev, ...rows] : rows))
          setNextOffset(offset + rows.length)
        } else {
          showNotice(t('page.players.load_failed'), 'error')
        }
      } catch (e: unknown) {
        if (isCancel(e)) return
        showNotice(t('page.players.load_failed'), 'error')
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [filter, search, showNotice, t, tab]
  )

  const reloadPlayers = useCallback(() => fetchPlayers(0, false), [fetchPlayers])
  const loadMore = useCallback(() => fetchPlayers(nextOffset, true), [fetchPlayers, nextOffset])

  const loadBots = useCallback(async () => {
    setBotsLoading(true)
    try {
      const { data } = await api.get('/players/bots')
      if (data.status === 'success' && Array.isArray(data.bots)) {
        setBots(data.bots as PlayerRow[])
        setServerRunning(!!data.server_running)
      }
    } catch (e: unknown) {
      if (isCancel(e)) return
      showNotice(t('page.players.load_failed'), 'error')
    } finally {
      setBotsLoading(false)
    }
  }, [showNotice, t])

  const loadWhitelist = useCallback(async () => {
    setWhitelistLoading(true)
    try {
      const { data } = await api.get('/players/whitelist')
      if (data.status === 'success') {
        setWhitelist(data as WhitelistData)
      }
    } catch (e: unknown) {
      if (isCancel(e)) return
      showNotice(t('page.players.load_failed'), 'error')
    } finally {
      setWhitelistLoading(false)
    }
  }, [showNotice, t])

  const loadOps = useCallback(async () => {
    setOpsLoading(true)
    try {
      const { data } = await api.get('/players/ops')
      if (data.status === 'success') {
        setOps(data as OpsData)
      }
    } catch (e: unknown) {
      if (isCancel(e)) return
      showNotice(t('page.players.load_failed'), 'error')
    } finally {
      setOpsLoading(false)
    }
  }, [showNotice, t])

  const loadBans = useCallback(async () => {
    setBansLoading(true)
    try {
      const { data } = await api.get('/players/bans')
      if (data.status === 'success') {
        setBans(data as BansData)
      }
    } catch (e: unknown) {
      if (isCancel(e)) return
      showNotice(t('page.players.load_failed'), 'error')
    } finally {
      setBansLoading(false)
    }
  }, [showNotice, t])

  // 玩家列表加载（带防抖）
  useEffect(() => {
    if (tab !== 'players' && tab !== 'all') return
    const timer = window.setTimeout(() => {
      void reloadPlayers()
    }, 250)
    return () => window.clearTimeout(timer)
  }, [tab, search, filter, reloadPlayers])

  // 假人 / 白名单 / OP / 封禁 初次加载
  useEffect(() => {
    if (tab === 'bots') void loadBots()
    else if (tab === 'whitelist') void loadWhitelist()
    else if (tab === 'ops') void loadOps()
    else if (tab === 'bans') void loadBans()
  }, [tab, loadBans, loadBots, loadOps, loadWhitelist])

  // 玩家 / 假人列表自动刷新
  useEffect(() => {
    if (tab !== 'players' && tab !== 'all' && tab !== 'bots') return
    const interval = window.setInterval(() => {
      if (tab === 'players' || tab === 'all') void reloadPlayers()
      else void loadBots()
    }, 15000)
    return () => window.clearInterval(interval)
  }, [tab, loadBots, reloadPlayers])

  const refreshTab = useCallback(async () => {
    if (tab === 'players' || tab === 'all') await reloadPlayers()
    else if (tab === 'bots') await loadBots()
    else if (tab === 'whitelist') await loadWhitelist()
    else if (tab === 'ops') await loadOps()
    else if (tab === 'bans') await loadBans()
  }, [tab, loadBans, loadBots, loadOps, reloadPlayers, loadWhitelist])

  const runAction = useCallback(
    async (
      key: string,
      fn: () => Promise<{ data: { status?: string; message?: string } }>,
      opts?: { successMsg?: string; reload?: boolean }
    ): Promise<boolean> => {
      if (actionLoading) return false
      setActionLoading(key)
      try {
        const { data } = await fn()
        if (data.status === 'success') {
          showNotice(opts?.successMsg || data.message || t('page.players.msg.success'), 'success')
          if (opts?.reload !== false) await refreshTab()
          return true
        }
        showNotice(data.message || t('page.players.msg.action_failed'), 'error')
        return false
      } catch (e: unknown) {
        if (isCancel(e)) return false
        showNotice(t('page.players.msg.action_failed'), 'error')
        return false
      } finally {
        setActionLoading(null)
      }
    },
    [actionLoading, refreshTab, showNotice, t]
  )

  // ---------- 行内操作 ----------

  const handleToggleOp = (p: PlayerRow) =>
    void runAction(`op:${p.name}`, () =>
      api.post(p.is_op ? '/players/deop' : '/players/op', { name: p.name })
    )

  const handleToggleWhitelist = (p: PlayerRow) =>
    void runAction(`wl:${p.name}`, () =>
      api.post(p.whitelisted ? '/players/whitelist/remove' : '/players/whitelist/add', { name: p.name })
    )

  const handleUnban = (p: PlayerRow) => setUnbanModal({ type: 'player', target: p.name })

  const confirmBan = async (target: string, type: 'player' | 'ip', reason: string) => {
    setBanModal(null)
    await runAction(`ban:${target}`, () => api.post('/players/ban', { target, type, reason }))
  }

  const confirmUnban = async () => {
    if (!unbanModal) return
    const { type, target } = unbanModal
    setUnbanModal(null)
    await runAction(`unban:${target}`, () => api.post('/players/unban', { target, type }))
  }

  const confirmKick = async (reason: string) => {
    if (!kickModal) return
    const name = kickModal.name
    setKickModal(null)
    await runAction(`kick:${name}`, () => api.post('/players/kick', { name, reason }))
  }

  // ---------- 白名单 / OP / 封禁页操作 ----------

  const handleWhitelistSet = (enabled: boolean) =>
    void runAction(`wlset:${enabled}`, () => api.post('/players/whitelist/set', { enabled }))

  const handleWhitelistReload = () =>
    void runAction('wlreload', () => api.post('/players/whitelist/reload'))

  const handleWhitelistAdd = async () => {
    const name = newMember.trim()
    if (!name) return
    const ok = await runAction('wladd', () => api.post('/players/whitelist/add', { name }))
    if (ok) setNewMember('')
  }

  const handleWhitelistRemove = (name: string) =>
    void runAction(`wlremove:${name}`, () => api.post('/players/whitelist/remove', { name }))

  const handleOpAdd = async () => {
    const name = newOpName.trim()
    if (!name) return
    const ok = await runAction('opadd', () => api.post('/players/op', { name }))
    if (ok) setNewOpName('')
  }

  const handleOpRemove = (name: string) =>
    void runAction(`deop:${name}`, () => api.post('/players/deop', { name }))

  const handleBanForm = async () => {
    const target = banForm.target.trim()
    if (!target) return
    const ok = await runAction(
      'banform',
      () => api.post('/players/ban', { target, type: banForm.type, reason: banForm.reason.trim() })
    )
    if (ok) setBanForm((f) => ({ ...f, target: '', reason: '' }))
  }

  // ---------- 格式化 ----------

  const fmtDuration = (seconds?: number | null) => {
    if (seconds == null || Number.isNaN(seconds) || seconds < 0) return '—'
    const s = Math.floor(seconds)
    const d = Math.floor(s / 86400)
    const h = Math.floor((s % 86400) / 3600)
    const m = Math.floor((s % 3600) / 60)
    if (d > 0) return t('page.players.duration.days', { d, h })
    if (h > 0) return t('page.players.duration.hours', { h, m })
    if (m > 0) return t('page.players.duration.minutes', { m })
    return t('page.players.duration.seconds', { s })
  }

  const fmtTime = (ts?: number | null) => {
    if (!ts) return '—'
    try {
      return new Date(ts * 1000).toLocaleString()
    } catch {
      return '—'
    }
  }

  const dimensionLabel = (dim?: string | null) => {
    if (!dim) return '—'
    if (dim.includes('overworld')) return t('page.players.dimension.overworld')
    if (dim.includes('nether')) return t('page.players.dimension.nether')
    if (dim.includes('the_end') || dim.includes('end')) return t('page.players.dimension.end')
    return dim.split(':').pop() || dim
  }

  const renderRowActions = (p: PlayerRow) => (
    <div className="flex items-center gap-0.5 justify-end">
      {!p.is_bot && (
        <ActionBtn
          title={p.is_op ? t('page.players.actions.unset_op') : t('page.players.actions.set_op')}
          tone={p.is_op ? 'amber' : 'green'}
          loading={actionLoading === `op:${p.name}`}
          onClick={() => handleToggleOp(p)}
        >
          {p.is_op ? <ShieldOff className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
        </ActionBtn>
      )}
      {p.online && (
        <ActionBtn
          title={t('page.players.actions.kick')}
          tone="amber"
          loading={actionLoading === `kick:${p.name}`}
          onClick={() => setKickModal({ name: p.name })}
        >
          <UserX className="w-4 h-4" />
        </ActionBtn>
      )}
      {!p.is_bot && (
        <ActionBtn
          title={p.whitelisted ? t('page.players.actions.whitelist_remove') : t('page.players.actions.whitelist_add')}
          tone={p.whitelisted ? 'rose' : 'blue'}
          loading={actionLoading === `wl:${p.name}`}
          onClick={() => handleToggleWhitelist(p)}
        >
          <ListChecks className="w-4 h-4" />
        </ActionBtn>
      )}
      {p.banned ? (
        <ActionBtn
          title={t('page.players.actions.unban')}
          tone="rose"
          loading={actionLoading === `unban:${p.name}`}
          onClick={() => handleUnban(p)}
        >
          <Undo2 className="w-4 h-4" />
        </ActionBtn>
      ) : (
        <ActionBtn
          title={t('page.players.actions.ban')}
          tone="rose"
          onClick={() => setBanModal({ name: p.name, ip: p.ip || null })}
        >
          <Ban className="w-4 h-4" />
        </ActionBtn>
      )}
    </div>
  )

  const renderBotsActions = (p: PlayerRow) => (
    <div className="flex items-center gap-0.5 justify-end">
      {p.online && (
        <ActionBtn
          title={t('page.players.actions.kick')}
          tone="amber"
          loading={actionLoading === `kick:${p.name}`}
          onClick={() => setKickModal({ name: p.name })}
        >
          <UserX className="w-4 h-4" />
        </ActionBtn>
      )}
    </div>
  )

  const PlayerTable: React.FC<{
    rows: PlayerRow[]
    loading: boolean
    emptyText: string
    renderActions?: (p: PlayerRow) => React.ReactNode
    footer?: React.ReactNode
  }> = ({ rows, loading, emptyText, renderActions, footer }) => (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-800/40">
            <th className="px-4 py-3 whitespace-nowrap">{t('page.players.col.player')}</th>
            <th className="px-4 py-3 whitespace-nowrap">{t('page.players.col.status')}</th>
            <th className="px-4 py-3 whitespace-nowrap">{t('page.players.col.ip')}</th>
            <th className="px-4 py-3 whitespace-nowrap">{t('page.players.col.online_duration')}</th>
            <th className="px-4 py-3 whitespace-nowrap">{t('page.players.col.last_seen')}</th>
            <th className="px-4 py-3 whitespace-nowrap">{t('page.players.col.location')}</th>
            <th className="px-4 py-3 whitespace-nowrap">{t('page.players.col.uuid')}</th>
            {renderActions && (
              <th className="px-4 py-3 whitespace-nowrap text-right">{t('page.players.col.actions')}</th>
            )}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            Array.from({ length: 6 }).map((_, i) => <TableRowSkeleton key={i} cols={renderActions ? 8 : 7} />)
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={renderActions ? 8 : 7} className="px-4 py-10 text-center text-slate-500 dark:text-slate-400">
                {emptyText}
              </td>
            </tr>
          ) : (
            rows.map((p) => (
              <tr
                key={p.uuid || p.name}
                className="border-b border-slate-100 dark:border-slate-800/80 last:border-0 hover:bg-slate-50/80 dark:hover:bg-slate-800/30"
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1.5 flex-wrap max-w-[14rem]">
                    <span className="font-semibold text-slate-900 dark:text-white truncate" title={p.name}>
                      {p.name}
                    </span>
                    {p.is_bot && (
                      <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold border ${badgeClass('amber')}`}>
                        {t('page.players.status.bot')}
                      </span>
                    )}
                    {p.is_op && (
                      <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold border ${badgeClass('green')}`}>
                        OP
                      </span>
                    )}
                    {p.whitelisted && (
                      <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold border ${badgeClass('blue')}`}>
                        {t('page.players.status.whitelisted')}
                      </span>
                    )}
                    {p.banned && (
                      <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold border ${badgeClass('rose')}`}>
                        {t('page.players.status.banned')}
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <span
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold border ${
                      p.online ? badgeClass('green') : badgeClass('slate')
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${p.online ? 'bg-green-500 animate-pulse' : 'bg-slate-400'}`} />
                    {p.online ? t('page.players.status.online') : t('page.players.status.offline')}
                  </span>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-300 whitespace-nowrap">
                  {p.ip ? (
                    <span title={p.ips.join('\n')} className="cursor-help">
                      {p.ip}
                    </span>
                  ) : (
                    '—'
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-300 whitespace-nowrap">
                  {p.online ? (
                    <>
                      <span className="text-slate-900 dark:text-white font-medium">
                        {t('page.players.session')} {fmtDuration(p.session_seconds)}
                      </span>
                      {p.total_playtime != null && (
                        <div className="text-slate-400 dark:text-slate-500">
                          {t('page.players.total_playtime')} {fmtDuration(p.total_playtime)}
                        </div>
                      )}
                    </>
                  ) : p.total_playtime != null ? (
                    fmtDuration(p.total_playtime)
                  ) : (
                    '—'
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                  {p.online ? t('page.players.status.online') : fmtTime(p.last_seen)}
                </td>
                <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-300 whitespace-nowrap">
                  {p.position ? (
                    <span title={p.dimension || ''}>
                      {dimensionLabel(p.dimension)} ({p.position.x}, {p.position.y}, {p.position.z})
                    </span>
                  ) : p.dimension ? (
                    dimensionLabel(p.dimension)
                  ) : (
                    '—'
                  )}
                </td>
                <td className="px-4 py-3 font-mono text-[11px] text-slate-400 dark:text-slate-500 whitespace-nowrap" title={p.uuid || ''}>
                  {shortUuid(p.uuid)}
                </td>
                {renderActions && <td className="px-4 py-3">{renderActions(p)}</td>}
              </tr>
            ))
          )}
        </tbody>
      </table>
      {footer}
    </div>
  )

  return (
    <>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
        {/* 页头 */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-emerald-500 rounded-2xl text-white shadow-lg shadow-emerald-500/25">
              <Users className="w-7 h-7" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 dark:text-white">{t('page.players.title')}</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">{t('page.players.subtitle')}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void refreshTab()}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 text-sm font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 transition-colors"
          >
            <RotateCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            {t('common.refresh')}
          </button>
        </div>

        {/* 标签页 */}
        <div className="flex gap-1 p-1 rounded-2xl bg-slate-100 dark:bg-slate-800 w-fit max-w-full overflow-x-auto">
          {TABS.map((item) => {
            const active = tab === item.key
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => setTab(item.key)}
                className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold whitespace-nowrap transition-all ${
                  active
                    ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                }`}
              >
                <item.icon className="w-4 h-4" />
                {t(item.labelKey)}
              </button>
            )
          })}
        </div>

        {(tab === 'players' || tab === 'all') && !serverRunning && (
          <div className="flex items-start gap-2 px-4 py-3 rounded-2xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 text-sm">
            <span className="shrink-0 mt-0.5">⚠</span>
            <div>
              <p className="font-semibold">{t('page.players.server_offline')}</p>
              <p className="text-xs mt-0.5">{t('page.players.server_offline_tip')}</p>
            </div>
          </div>
        )}

        {/* 全部 / 玩家 */}
        {(tab === 'all' || tab === 'players') && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1 min-w-0">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t('page.players.search_placeholder')}
                  className="w-full pl-9 pr-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/60"
                />
              </div>
              <div className="w-full sm:w-48 shrink-0">
                <NiceSelect
                  value={filter}
                  onChange={setFilter}
                  options={[
                    { value: 'all', label: t('page.players.filters.all') },
                    { value: 'online', label: t('page.players.filters.online') },
                    { value: 'offline', label: t('page.players.filters.offline') },
                    ...(tab === 'all'
                      ? [{ value: 'bot', label: t('page.players.filters.bot') }]
                      : []),
                    { value: 'op', label: t('page.players.filters.op') },
                  ]}
                />
              </div>
            </div>

            <p className="text-xs text-slate-500 dark:text-slate-400 px-1">
              {tab === 'players'
                ? t('page.players.count_players', { total, online: onlineCount })
                : t('page.players.count', { total, online: onlineCount, bots: botCount })}
            </p>

            <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
              <PlayerTable
                rows={players}
                loading={loading && players.length === 0}
                emptyText={t('page.players.empty')}
                renderActions={renderRowActions}
                footer={
                  !loading && players.length > 0 && nextOffset < total ? (
                    <div className="p-4 border-t border-slate-200 dark:border-slate-800 flex justify-center">
                      <button
                        type="button"
                        disabled={loadingMore}
                        onClick={() => void loadMore()}
                        className="px-5 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-100 text-sm font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 inline-flex items-center gap-2"
                      >
                        {loadingMore && <RotateCw className="w-4 h-4 animate-spin" />}
                        {t('page.players.load_more')}
                      </button>
                    </div>
                  ) : null
                }
              />
            </div>
          </div>
        )}

        {/* 假人 */}
        {tab === 'bots' && (
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
            <PlayerTable
              rows={bots}
              loading={botsLoading}
              emptyText={t('page.players.bots_empty')}
              renderActions={renderBotsActions}
            />
          </div>
        )}

        {/* 白名单 */}
        {tab === 'whitelist' && (
          <div className="space-y-6">
            <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm p-6">
              <div className="flex items-center justify-between flex-wrap gap-4">
                <div className="flex items-center gap-3">
                  <div className={`p-2.5 rounded-xl text-white shadow-lg ${whitelist?.enabled ? 'bg-emerald-500 shadow-emerald-500/25' : 'bg-slate-400 shadow-slate-400/25'}`}>
                    <ListChecks className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-slate-900 dark:text-white">{t('page.players.whitelist.title')}</h3>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
                      {whitelistLoading
                        ? t('common.notice_loading')
                        : whitelist?.enabled
                          ? t('page.players.whitelist.enabled')
                          : t('page.players.whitelist.disabled')}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleWhitelistReload()}
                    disabled={actionLoading === 'wlreload'}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 text-sm font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 transition-colors"
                  >
                    <RotateCw className={`w-4 h-4 ${actionLoading === 'wlreload' ? 'animate-spin' : ''}`} />
                    {t('page.players.actions.reload')}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleWhitelistSet(!whitelist?.enabled)}
                    disabled={actionLoading === 'wlset:true' || actionLoading === 'wlset:false' || whitelistLoading}
                    className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-white text-sm font-semibold transition-colors disabled:opacity-50 ${
                      whitelist?.enabled ? 'bg-rose-500 hover:bg-rose-600' : 'bg-emerald-600 hover:bg-emerald-700'
                    }`}
                  >
                    {whitelist?.enabled ? t('page.players.whitelist.disable') : t('page.players.whitelist.enable')}
                  </button>
                </div>
              </div>
            </div>

            <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm p-6">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <h3 className="font-bold text-slate-900 dark:text-white">{t('page.players.whitelist.members')}</h3>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t('page.players.whitelist.member_count', { count: whitelist?.members.length ?? 0 })}
                </span>
              </div>
              <div className="flex flex-col sm:flex-row gap-2 mt-4">
                <input
                  value={newMember}
                  onChange={(e) => setNewMember(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void handleWhitelistAdd()
                  }}
                  placeholder={t('page.players.whitelist.add_placeholder')}
                  className="flex-1 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/60"
                />
                <button
                  type="button"
                  onClick={() => void handleWhitelistAdd()}
                  disabled={actionLoading === 'wladd' || !newMember.trim()}
                  className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold disabled:opacity-50 transition-colors"
                >
                  {actionLoading === 'wladd' ? <RotateCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                  {t('common.add')}
                </button>
              </div>
              <div className="mt-4 space-y-2">
                {whitelistLoading ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-14 w-full rounded-2xl" />
                  ))
                ) : (whitelist?.members.length ?? 0) === 0 ? (
                  <p className="py-8 text-center text-slate-500 dark:text-slate-400 text-sm">{t('page.players.whitelist.empty')}</p>
                ) : (
                  whitelist?.members.map((m) => (
                    <div
                      key={m.uuid || m.name}
                      className="flex items-center justify-between gap-3 p-3 rounded-2xl bg-slate-50 dark:bg-slate-800/60"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{m.name || m.uuid}</p>
                        <p className="font-mono text-[11px] text-slate-400 dark:text-slate-500 truncate">{m.uuid}</p>
                      </div>
                      <ActionBtn
                        title={t('page.players.actions.remove')}
                        tone="rose"
                        loading={actionLoading === `wlremove:${m.name}`}
                        onClick={() => handleWhitelistRemove(m.name)}
                      >
                        <X className="w-4 h-4" />
                      </ActionBtn>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* OP */}
        {tab === 'ops' && (
          <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm p-6">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h3 className="font-bold text-slate-900 dark:text-white">{t('page.players.tabs.ops')}</h3>
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {t('page.players.ops.op_count', { count: ops?.ops.length ?? 0 })}
              </span>
            </div>
            <div className="flex flex-col sm:flex-row gap-2 mt-4">
              <input
                value={newOpName}
                onChange={(e) => setNewOpName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void handleOpAdd()
                }}
                placeholder={t('page.players.ops.add_placeholder')}
                className="flex-1 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/60"
              />
              <button
                type="button"
                onClick={() => void handleOpAdd()}
                disabled={actionLoading === 'opadd' || !newOpName.trim()}
                className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold disabled:opacity-50 transition-colors"
              >
                {actionLoading === 'opadd' ? <RotateCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                {t('common.add')}
              </button>
            </div>
            <div className="mt-4 space-y-2">
              {opsLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-14 w-full rounded-2xl" />
                ))
              ) : (ops?.ops.length ?? 0) === 0 ? (
                <p className="py-8 text-center text-slate-500 dark:text-slate-400 text-sm">{t('page.players.ops.empty')}</p>
              ) : (
                ops?.ops.map((op) => (
                  <div key={op.uuid || op.name} className="flex items-center justify-between gap-3 p-3 rounded-2xl bg-slate-50 dark:bg-slate-800/60">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-xl text-green-600 dark:text-green-400 shrink-0">
                        <ShieldCheck className="w-4 h-4" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{op.name}</p>
                        <p className="font-mono text-[11px] text-slate-400 dark:text-slate-500 truncate">{op.uuid}</p>
                      </div>
                      {op.level != null && (
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border shrink-0 ${badgeClass('slate')}`}>
                          {t('page.players.col.level')} {op.level}
                        </span>
                      )}
                    </div>
                    <ActionBtn
                      title={t('page.players.actions.unset_op')}
                      tone="rose"
                      loading={actionLoading === `deop:${op.name}`}
                      onClick={() => handleOpRemove(op.name)}
                    >
                      <ShieldOff className="w-4 h-4" />
                    </ActionBtn>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* 封禁 */}
        {tab === 'bans' && (
          <div className="space-y-6">
            <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm p-6">
              <h3 className="font-bold text-slate-900 dark:text-white">{t('page.players.bans.add_title')}</h3>
              <div className="flex flex-col lg:flex-row gap-2 mt-4">
                <div className="w-full sm:w-44 shrink-0">
                  <NiceSelect
                    value={banForm.type}
                    onChange={(v) => setBanForm((f) => ({ ...f, type: v }))}
                    options={[
                      { value: 'player', label: t('page.players.bans.type_player') },
                      { value: 'ip', label: t('page.players.bans.type_ip') },
                    ]}
                  />
                </div>
                <input
                  value={banForm.target}
                  onChange={(e) => setBanForm((f) => ({ ...f, target: e.target.value }))}
                  placeholder={t('page.players.bans.target_placeholder')}
                  className="flex-1 min-w-0 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/60"
                />
                <input
                  value={banForm.reason}
                  onChange={(e) => setBanForm((f) => ({ ...f, reason: e.target.value }))}
                  placeholder={t('page.players.bans.reason_placeholder')}
                  className="flex-1 min-w-0 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/60"
                />
                <button
                  type="button"
                  onClick={() => void handleBanForm()}
                  disabled={actionLoading === 'banform' || !banForm.target.trim()}
                  className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-sm font-semibold disabled:opacity-50 transition-colors"
                >
                  {actionLoading === 'banform' ? <RotateCw className="w-4 h-4 animate-spin" /> : <Ban className="w-4 h-4" />}
                  {t('page.players.bans.ban')}
                </button>
              </div>
            </div>

            <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm p-6">
              <h3 className="font-bold text-slate-900 dark:text-white mb-4">{t('page.players.bans.players_title')}</h3>
              {bansLoading ? (
                Array.from({ length: 2 }).map((_, i) => (
                  <Skeleton key={i} className="h-14 w-full rounded-2xl" />
                ))
              ) : bans?.players.length === 0 ? (
                <p className="py-6 text-center text-slate-500 dark:text-slate-400 text-sm">{t('page.players.bans.empty')}</p>
              ) : (
                <div className="space-y-2">
                  {bans?.players.map((b, idx) => (
                    <div key={`${b.name}-${idx}`} className="flex items-center justify-between gap-3 p-3 rounded-2xl bg-slate-50 dark:bg-slate-800/60">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">{b.name || b.uuid}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                          {b.reason || t('page.players.bans.not_set')}
                          {b.created ? ` · ${b.created}` : ''}
                        </p>
                      </div>
                      <ActionBtn
                        title={t('page.players.actions.unban')}
                        tone="rose"
                        loading={actionLoading === `unban:${b.name || b.uuid}`}
                        onClick={() => setUnbanModal({ type: 'player', target: b.name || b.uuid || '' })}
                      >
                        <Undo2 className="w-4 h-4" />
                      </ActionBtn>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-white dark:bg-slate-900 rounded-3xl border border-slate-200 dark:border-slate-800 shadow-sm p-6">
              <h3 className="font-bold text-slate-900 dark:text-white mb-4">{t('page.players.bans.ips_title')}</h3>
              {bansLoading ? (
                Array.from({ length: 2 }).map((_, i) => (
                  <Skeleton key={i} className="h-14 w-full rounded-2xl" />
                ))
              ) : bans?.ips.length === 0 ? (
                <p className="py-6 text-center text-slate-500 dark:text-slate-400 text-sm">{t('page.players.bans.empty')}</p>
              ) : (
                <div className="space-y-2">
                  {bans?.ips.map((b, idx) => (
                    <div key={`${b.ip}-${idx}`} className="flex items-center justify-between gap-3 p-3 rounded-2xl bg-slate-50 dark:bg-slate-800/60">
                      <div className="min-w-0">
                        <p className="text-sm font-mono font-semibold text-slate-900 dark:text-white truncate">{b.ip}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                          {b.reason || t('page.players.bans.not_set')}
                          {b.created ? ` · ${b.created}` : ''}
                        </p>
                      </div>
                      <ActionBtn
                        title={t('page.players.actions.unban')}
                        tone="rose"
                        loading={actionLoading === `unban:${b.ip}`}
                        onClick={() => setUnbanModal({ type: 'ip', target: b.ip || '' })}
                      >
                        <Undo2 className="w-4 h-4" />
                      </ActionBtn>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </motion.div>

      {/* 封禁弹窗 */}
      <AnimatePresence>
        {banModal && (
          <BanModal
            name={banModal.name}
            ip={banModal.ip}
            onClose={() => setBanModal(null)}
            onConfirm={confirmBan}
          />
        )}
      </AnimatePresence>

      {/* 解封确认弹窗（重启提示） */}
      <AnimatePresence>
        {unbanModal && (
          <UnbanModal
            target={unbanModal.target}
            type={unbanModal.type}
            onClose={() => setUnbanModal(null)}
            onConfirm={confirmUnban}
          />
        )}
      </AnimatePresence>

      {/* 踢出弹窗 */}
      <AnimatePresence>
        {kickModal && (
          <KickModal name={kickModal.name} onClose={() => setKickModal(null)} onConfirm={confirmKick} />
        )}
      </AnimatePresence>

      {/* 提示 */}
      {notice && (
        <div
          className={`fixed bottom-6 right-6 z-[70] max-w-sm px-4 py-3 rounded-2xl shadow-lg flex items-center gap-2 text-sm text-white ${
            notice.type === 'success' ? 'bg-emerald-500' : 'bg-rose-500'
          }`}
        >
          <span className="flex-1 min-w-0">{notice.msg}</span>
          <button type="button" onClick={() => setNotice(null)} className="text-white/80 hover:text-white shrink-0" aria-label={t('common.close')}>
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
    </>
  )
}

/* ------------------------- 弹窗组件 ------------------------- */

const ModalShell: React.FC<{
  title: string
  onClose: () => void
  children: React.ReactNode
  maxWidth?: string
}> = ({ title, onClose, children, maxWidth = 'max-w-md' }) => (
  <motion.div
    className="fixed inset-0 z-[60] bg-slate-900/60 flex items-center justify-center p-4"
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0 }}
    onClick={onClose}
  >
    <motion.div
      initial={{ opacity: 0, scale: 0.96, y: 8 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.96, y: 8 }}
      transition={{ duration: 0.15 }}
      className={`bg-white dark:bg-slate-900 rounded-3xl shadow-xl border border-slate-200 dark:border-slate-800 w-full ${maxWidth} p-6 space-y-4`}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-slate-900 dark:text-white">{title}</h3>
        <button
          type="button"
          onClick={onClose}
          className="p-2 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
          aria-label="close"
        >
          <X className="w-5 h-5" />
        </button>
      </div>
      {children}
    </motion.div>
  </motion.div>
)

const BanModal: React.FC<{
  name: string
  ip: string | null
  onClose: () => void
  onConfirm: (target: string, type: 'player' | 'ip', reason: string) => Promise<void>
}> = ({ name, ip, onClose, onConfirm }) => {
  const { t } = useTranslation()
  const [type, setType] = useState<'player' | 'ip'>('player')
  const [target, setTarget] = useState(name)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const switchType = (next: 'player' | 'ip') => {
    setType(next)
    if (next === 'ip' && ip) setTarget(ip)
    else if (next === 'player') setTarget(name)
  }

  const submit = async () => {
    if (!target.trim() || busy) return
    setBusy(true)
    try {
      await onConfirm(target.trim(), type, reason.trim())
    } finally {
      setBusy(false)
    }
  }

  return (
    <ModalShell
      title={type === 'ip' ? t('page.players.ban_modal.title_ip') : t('page.players.ban_modal.title_player')}
      onClose={onClose}
    >
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => switchType('player')}
          className={`flex-1 px-3 py-2 rounded-xl text-sm font-semibold transition-colors ${
            type === 'player'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
          }`}
        >
          {t('page.players.bans.type_player')}
        </button>
        <button
          type="button"
          onClick={() => switchType('ip')}
          disabled={!ip}
          className={`flex-1 px-3 py-2 rounded-xl text-sm font-semibold transition-colors disabled:opacity-40 ${
            type === 'ip'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
          }`}
        >
          {t('page.players.bans.type_ip')}
        </button>
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('page.players.ban_modal.target_label')}</label>
        <input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/60"
        />
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('page.players.bans.reason_placeholder')}</label>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void submit()
          }}
          placeholder={t('page.players.bans.reason_placeholder')}
          className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/60"
        />
      </div>
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={onClose}
          className="flex-1 px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
        >
          {t('common.cancel')}
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy || !target.trim()}
          className="flex-1 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-sm font-semibold text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors inline-flex items-center justify-center gap-2"
        >
          {busy ? <RotateCw className="w-4 h-4 animate-spin" /> : <Ban className="w-4 h-4" />}
          {t('page.players.ban_modal.confirm')}
        </button>
      </div>
    </ModalShell>
  )
}

const UnbanModal: React.FC<{
  target: string
  type: 'player' | 'ip'
  onClose: () => void
  onConfirm: () => Promise<void>
}> = ({ target, type, onClose, onConfirm }) => {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (busy) return
    setBusy(true)
    try {
      await onConfirm()
    } finally {
      setBusy(false)
    }
  }

  return (
    <ModalShell title={t('page.players.bans.unban_confirm_title')} onClose={onClose}>
      <p className="text-sm text-slate-700 dark:text-slate-300 break-all">
        {type === 'ip' ? t('page.players.bans.unban_ip_desc', { ip: target }) : t('page.players.bans.unban_player_desc', { name: target })}
      </p>
      <div className="rounded-2xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 p-3 text-xs text-amber-800 dark:text-amber-300">
        {t('page.players.bans.unban_warning')}
      </div>
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={onClose}
          className="flex-1 px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
        >
          {t('common.cancel')}
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy}
          className="flex-1 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-sm font-semibold text-white disabled:opacity-50 transition-colors inline-flex items-center justify-center gap-2"
        >
          {busy ? <RotateCw className="w-4 h-4 animate-spin" /> : <Undo2 className="w-4 h-4" />}
          {t('page.players.bans.unban_confirm')}
        </button>
      </div>
    </ModalShell>
  )
}

const KickModal: React.FC<{
  name: string
  onClose: () => void
  onConfirm: (reason: string) => Promise<void>
}> = ({ name, onClose, onConfirm }) => {
  const { t } = useTranslation()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (busy) return
    setBusy(true)
    try {
      await onConfirm(reason.trim())
    } finally {
      setBusy(false)
    }
  }

  return (
    <ModalShell title={t('page.players.kick_modal.title')} onClose={onClose}>
      <p className="text-sm text-slate-700 dark:text-slate-300 break-all">{t('page.players.kick_modal.desc', { name })}</p>
      <div className="space-y-2">
        <label className="text-sm font-medium text-slate-700 dark:text-slate-300">{t('page.players.kick_modal.reason_placeholder')}</label>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void submit()
          }}
          placeholder={t('page.players.kick_modal.reason_placeholder')}
          className="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/60"
        />
      </div>
      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={onClose}
          className="flex-1 px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
        >
          {t('common.cancel')}
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy}
          className="flex-1 px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-700 text-sm font-semibold text-white disabled:opacity-50 transition-colors inline-flex items-center justify-center gap-2"
        >
          {busy ? <RotateCw className="w-4 h-4 animate-spin" /> : <UserX className="w-4 h-4" />}
          {t('page.players.kick_modal.confirm')}
        </button>
      </div>
    </ModalShell>
  )
}

export default Players
