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