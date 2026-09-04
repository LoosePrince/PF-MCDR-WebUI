/**
 * 前后端共享 API 契约类型（单一类型源，杜绝两套手写类型漂移）。
 *
 * 基线：docs/WebApi.md；最终以后端 OpenAPI（GET /openapi.json）为准。
 * 后端 structures/envelope.py 的 TypedDict 与这里的接口一一对应，
 * 新增/修改字段时两侧同步修改。
 */

// ---------------------------------------------------------------- //
// 2.3 统一响应外壳

/** 统一成功外壳：{status: "success", message?, data?} */
export interface ApiSuccessEnvelope<T = unknown> {
  status: 'success'
  message?: string | null
  data?: T | null
}

/** 统一错误外壳：{status: "error", message, code, data?}（配非 2xx 状态码） */
export interface ApiErrorEnvelope {
  status: 'error'
  message: string
  code: string
  data?: unknown
}

export type ApiEnvelope<T = unknown> = ApiSuccessEnvelope<T> | ApiErrorEnvelope

/** 分页负载：data = {items, total, offset, limit}（PageData，见 envelope.page()） */
export interface PageData<T> {
  items: T[]
  total: number
  offset: number
  limit?: number | null
}

/** 分页成功外壳 */
export type PageEnvelope<T> = ApiSuccessEnvelope<PageData<T>>

// ---------------------------------------------------------------- //
// 公开聊天域

/** 聊天消息记录（GET /chat/messages → data.items） */
export interface ChatMessage {
  id: number
  player_id: string
  uuid?: string
  message: string
  /** epoch 秒（全库时间契约） */
  timestamp: number
  is_plugin: boolean
  is_rtext: boolean
  rtext_data?: unknown
  message_source: string
}

/** 在线状态（GET /chat/messages/incremental → data.online） */
export interface ChatOnlineStatus {
  web: string[]
  game: string[]
  bot: string[]
}

/** 验证码检查结果（GET /chat/verifications/{code} → data） */
export interface ChatVerificationStatus {
  verified: boolean
  player_id?: string
  message?: string
}

/** 聊天会话（PUT accounts/password、POST /chat/sessions → data） */
export interface ChatSessionData {
  session_id: string
  player_id?: string
  uuid?: string
  message?: string
}

// ---------------------------------------------------------------- //
// 操作审计域

/** 审计操作者（data.items[].account） */
export interface AuditAccount {
  username?: string | null
  nickname?: string | null
  auth_via?: string | null
}

/** 审计记录（GET /audit_logs → data.items） */
export interface AuditRecord {
  id?: string
  /** epoch 秒（整型） */
  ts?: number
  operation_type?: string
  summary?: string
  detail?: unknown
  account?: AuditAccount | null
}

// ---------------------------------------------------------------- //
// 服务器域

/** 服务器状态（GET /server/status → data）：online 为顶层布尔（status 双义已消除） */
export interface ServerStatus {
  online: boolean
  version?: string | null
  players?: string | null
}
