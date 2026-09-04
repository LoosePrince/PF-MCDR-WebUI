import axios from 'axios'

/**
 * 动态获取基础路径
 * 支持独立运行模式 (/) 和 fastapi_mcdr 挂载模式 (/guguwebui)
 */
export const getBasePath = () => {
  // 优先从后端注入的全局变量获取
  if ((window as any).__GUGU_CONFIG__?.root_path) {
    return (window as any).__GUGU_CONFIG__.root_path
  }

  // 备选方案：根据当前路径分析
  const pathname = window.location.pathname
  // 如果路径以 /guguwebui 开头，则认为基础路径是 /guguwebui
  // 这里可以根据实际挂载点进行调整，或者让后端注入
  if (pathname.startsWith('/guguwebui')) {
    return '/guguwebui'
  }
  return ''
}

const instance = axios.create({
  baseURL: `${getBasePath()}/api`,
  timeout: 30000,
})

const TARGET_SERVER_KEY = 'target_server_id'

export const getTargetServerId = (): string => {
  try {
    return localStorage.getItem(TARGET_SERVER_KEY) || 'local'
  } catch {
    return 'local'
  }
}

export const setTargetServerId = (serverId: string) => {
  try {
    localStorage.setItem(TARGET_SERVER_KEY, serverId || 'local')
  } catch {}
}

/** 主服代理子服不可达时后端返回的 JSON（见 panel_merge/proxy.py） */
export const SLAVE_OFFLINE_EVENT = 'gugu:slaveOffline'

function isSlaveOfflineResponse(error: unknown): boolean {
  const ax = error as {
    response?: { status?: number; data?: unknown }
  }
  if (ax.response?.status !== 502) return false
  const d = ax.response.data
  if (!d || typeof d !== 'object') return false
  const o = d as Record<string, unknown>
  if (o.code === 'slave_offline') return true
  if (o.message === 'Slave unreachable') return true
  return false
}

function requestExplicitlyLocal(config: { headers?: unknown } | undefined): boolean {
  const h = config?.headers as Record<string, unknown> | undefined
  if (!h) return false
  const v = h['X-Target-Server'] ?? h['x-target-server']
  return v === 'local'
}

let lastSlaveOfflineSwitchAt = 0
const SLAVE_OFFLINE_DEBOUNCE_MS = 1500
const NO_REDIRECT_ON_401_PATH_SUFFIXES = ['/login', '/player-chat']

function shouldSkip401Redirect(pathname: string): boolean {
  return NO_REDIRECT_ON_401_PATH_SUFFIXES.some((suffix) => pathname.endsWith(suffix))
}

// 请求拦截器：注入目标服务器（多服面板合并）
instance.interceptors.request.use((config) => {
  const sid = getTargetServerId()
  const existing = (config.headers as any)?.['X-Target-Server']
  if (!existing && sid && sid !== 'local') {
    config.headers = config.headers || {}
    ;(config.headers as any)['X-Target-Server'] = sid
  }
  return config
})

// 响应拦截器：处理 401 未授权错误；子服离线时切回本地并提示
instance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 未授权时默认跳登录页，但公共玩家聊天页允许匿名访问
      if (!shouldSkip401Redirect(window.location.pathname)) {
        window.location.href = `${getBasePath()}/login`
      }
    } else if (
      isSlaveOfflineResponse(error) &&
      !requestExplicitlyLocal(error.config) &&
      getTargetServerId() !== 'local'
    ) {
      setTargetServerId('local')
      const now = Date.now()
      if (now - lastSlaveOfflineSwitchAt >= SLAVE_OFFLINE_DEBOUNCE_MS) {
        lastSlaveOfflineSwitchAt = now
        try {
          window.dispatchEvent(new CustomEvent(SLAVE_OFFLINE_EVENT))
        } catch {
          /* ignore */
        }
      }
    }
    return Promise.reject(error)
  }
)

export const isCancel = axios.isCancel

/**
 * 从任意 axios 错误/后端错误体中提取可展示信息。
 * 兼容历史多套错误体：
 *  - {status:error, message, code?, data?}（统一错误体）
 *  - {detail: string | [...]}（FastAPI 默认 HTTPException / 422）
 *  - 无响应体（网络层错误）
 */
export const getApiErrorMessage = (
  error: unknown,
  fallback = 'Request failed'
): string => {
  if (!error) return fallback
  if (typeof error === 'string') return error
  const e = error as {
    message?: string
    response?: { data?: unknown; status?: number; statusText?: string }
  }
  const data = e.response?.data
  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>
    if (typeof d.message === 'string' && d.message) return d.message
    if (typeof d.detail === 'string' && d.detail) return d.detail
  }
  if (typeof e.message === 'string' && e.message) return e.message
  if (e.response?.statusText) return `${e.response.statusText} (${e.response.status ?? ''})`.trim()
  return fallback
}

/**
 * 解包统一成功体：优先返回 data 字段；旧接口（负载在顶层）直接返回原 data。
 * 分域迁移期间两类接口并存，新代码一律经此函数取值。
 */
export const unwrapData = <T>(resp: { data: unknown }, fallback?: T): T => {
  const d = resp.data
  if (d && typeof d === 'object') {
    const o = d as Record<string, unknown>
    if (o.status === 'success' && 'data' in o) return (o.data as T) ?? (fallback as T)
  }
  return (d as T) ?? (fallback as T)
}

export default instance
