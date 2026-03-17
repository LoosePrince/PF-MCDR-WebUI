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

// 响应拦截器：处理 401 未授权错误
instance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 如果未授权且不在登录页，跳转到登录页
      if (!window.location.pathname.endsWith('/login')) {
        window.location.href = `${getBasePath()}/login`
      }
    }
    return Promise.reject(error)
  }
)

export const isCancel = axios.isCancel
export default instance
