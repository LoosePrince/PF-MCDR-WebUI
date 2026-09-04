/** 服务器状态数值格式化工具 */

const isNumber = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)

export const formatBytes = (bytes: number | null | undefined, digits = 1): string => {
  if (!isNumber(bytes)) return '—'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : digits)} ${units[i]}`
}

/** 坐标轴紧凑格式，如 1.2M/s */
export const formatSpeedShort = (bps: number | null | undefined): string => {
  if (!isNumber(bps)) return '—'
  if (bps < 1024) return `${Math.round(bps)}B/s`
  const units = ['K', 'M', 'G', 'T']
  const i = Math.min(units.length - 1, Math.floor(Math.log(bps) / Math.log(1024)) - 1)
  if (i < 0) return `${Math.round(bps)}B/s`
  return `${(bps / 1024 ** (i + 1)).toFixed(1)}${units[i]}/s`
}

export const formatSpeed = (bps: number | null | undefined): string => formatSpeedShort(bps)

export const formatPercent = (v: number | null | undefined, digits = 1): string => {
  if (!isNumber(v)) return '—'
  return `${v.toFixed(digits)}%`
}

export const formatTps = (v: number | null | undefined): string => {
  if (!isNumber(v)) return '—'
  return v.toFixed(1)
}

export const formatMspt = (v: number | null | undefined): string => {
  if (!isNumber(v)) return '—'
  return `${v.toFixed(1)} ms`
}

export const formatLoad = (v: number | null | undefined): string => {
  if (!isNumber(v)) return '—'
  return v.toFixed(2)
}

export const formatUptime = (sec: number | null | undefined): string => {
  if (!isNumber(sec) || sec < 0) return '—'
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m ${Math.floor(sec % 60)}s`
}

/** 折线图 Y 轴紧凑格式：百分比 */
export const percentAxisTick = (v: number) => `${Math.round(v)}%`

/** 折线图 Y 轴紧凑格式：网络速度 */
export const speedAxisTick = (v: number) => formatSpeedShort(v)

/** 折线图时间轴格式；long 模式带日期（用于 12h 以上范围） */
export const formatTimeAxis = (ts: number, long: boolean): string => {
  if (!isNumber(ts)) return ''
  const d = new Date(ts * 1000)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  if (long) {
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${hh}:${mm}`
  }
  return `${hh}:${mm}`
}

// ---------------------------------------------------------------- //
// epoch 秒集中格式化（时间字段全库收敛为 epoch 秒的补充工具）

export const isValidEpoch = (sec?: number | null): sec is number =>
  typeof sec === 'number' && Number.isFinite(sec) && sec > 0

/**
 * 将后端时间字段（统一 epoch 秒）或历史 ISO/可解析字符串归一为 epoch 秒。
 * 数字按 epoch 秒处理；解析失败返回 null。
 */
export const toEpoch = (v?: number | string | null): number | null => {
  if (typeof v === 'number') return Number.isFinite(v) && v > 0 ? Math.floor(v) : null
  if (typeof v === 'string' && v) {
    const ms = Date.parse(v)
    return Number.isFinite(ms) ? Math.floor(ms / 1000) : null
  }
  return null
}

/** epoch 秒 → 本地化完整时间（含日期）；无效输入返回 fallback。 */
export const formatEpoch = (sec?: number | null, fallback = '—'): string => {
  if (!isValidEpoch(sec)) return fallback
  try {
    return new Date(sec * 1000).toLocaleString()
  } catch {
    return fallback
  }
}

/** epoch 秒 → 本地化日期（无时间）；无效输入返回 fallback。 */
export const formatEpochDate = (sec?: number | null, fallback = '—'): string => {
  if (!isValidEpoch(sec)) return fallback
  try {
    return new Date(sec * 1000).toLocaleDateString()
  } catch {
    return fallback
  }
}

/** 秒数 → "xx天 xx小时 xx分钟"（不足一分钟显示秒数）；秒数为 0 显示 "0秒"。 */
export const formatDuration = (sec?: number | null, fallback = '—'): string => {
  if (sec === 0) return '0秒'
  if (!isValidEpoch(sec)) return fallback
  const total = Math.max(0, Math.floor(sec))
  const d = Math.floor(total / 86400)
  const h = Math.floor((total % 86400) / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const parts: string[] = []
  if (d > 0) parts.push(`${d}天`)
  if (h > 0) parts.push(`${h}小时`)
  if (m > 0) parts.push(`${m}分钟`)
  if (parts.length === 0) parts.push(`${s}秒`)
  return parts.join(' ')
}

/** 字节数 → 人类可读大小（B/KB/MB/GB/TB）；沿用既有 formatBytes 风格。 */
export const formatFileSize = (bytes?: number | null, fallback = '—'): string => {
  if (!isNumber(bytes) || bytes < 0) return fallback
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}