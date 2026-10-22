/**
 * API 类型定义:与 docs/02-API约定.md 及后端 app/schemas/ 保持一致的 Source of Truth。
 */

/** 统一响应包络 */
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T | null
}

/** 用户摘要 */
export interface UserSummary {
  user_id: number
  name: string
  avatar: string | null
  online: boolean
}

/** 用户完整资料 */
export interface UserProfile {
  user_id: number
  name: string
  avatar: string | null
  email: string | null
  phone: string | null
  register_time: number
  login_time: number | null
}

export interface UserSearchOut {
  items: UserSummary[]
}

// ---------- 认证 ----------

export interface LoginIn {
  name: string
  password: string
}

export interface LoginOut {
  token: string
  user: UserSummary
}

// ---------- 好友 ----------

export interface FriendItem {
  user_id: number
  name: string
  avatar: string | null
  remark: string | null
  group_name: string | null
  online: boolean
}

export interface FriendListOut {
  items: FriendItem[]
}

export interface FriendRequest {
  request_id: number
  from_user: UserSummary | null
  to_user_id: number
  status: 'pending' | 'accepted' | 'rejected'
  create_time: number
}

export interface FriendRequestListOut {
  items: FriendRequest[]
}

// ---------- 会话 ----------

export interface Member {
  user: UserSummary
  role: 'owner' | 'admin' | 'member'
  join_time: number
}

export interface Conversation {
  conversation_id: number
  name: string | null
  type: 'private' | 'group'
  avatar: string | null
  owner_id: number | null
  announcement: string | null
  members: Member[]
  create_time: number
  update_time: number
}

export interface Message {
  msg_id: number
  conversation_id: number
  sender_id: number | null
  body: string
  reply_to: number | null
  create_time: number
  /**
   * 该消息在「我的」用户链上的 seq,仅会话历史会返回。
   * 上报已读时必须用它作为 read_index —— 不能用 msg_id(全局 ID ≠ 我的 seq)。
   */
  seq?: number
}

export interface ConversationItem {
  conversation_id: number
  name: string | null
  type: 'private' | 'group'
  avatar: string | null
  member_count: number
  last_msg: Message | null
  unread_count: number
  pinned: boolean
  muted: boolean
  update_time: number
}

export interface ConversationListOut {
  items: ConversationItem[]
}

// ---------- 消息与同步 ----------

export interface HistoryOut {
  items: Message[]
  next_cursor: number | null
}

export interface SyncItem {
  seq: number
  kind: 'message' | 'recall' | 'read' | 'delete'
  conversation_id: number
  data: Record<string, unknown> | null
}

export interface SyncOut {
  items: SyncItem[]
  next_cursor: number | null
}

// ---------- WebSocket 事件 ----------

export interface WsMessageNewEvent {
  type: 'message.new'
  /** 本端用户链上一条消息的 seq,用于连续性校验 */
  prev_seq: number
  /** 本端新消息的 seq */
  seq: number
  data: Message
}

export interface WsMessageRecallEvent {
  type: 'message.recall'
  seq: number
  prev_seq: number
  data: { msg_id: number; conversation_id: number }
}

/** 本端多设备同步删除:我在某设备本地删除了一条消息 */
export interface WsMessageDeleteEvent {
  type: 'message.delete'
  seq: number
  prev_seq: number
  data: { msg_id: number; conversation_id: number }
}

export interface WsReadSyncEvent {
  type: 'read.sync'
  /** 本次已读上报占用的用户链 seq;与 message.new 同一套连续性校验 */
  seq: number
  prev_seq: number
  data: { conversation_id: number; read_index: number }
}

export interface WsFriendRequestEvent {
  type: 'friend.request'
  data: FriendRequest
}

export interface WsConversationUpdateEvent {
  type: 'conversation.update'
  data: Conversation
}

export type WsEvent =
  | WsMessageNewEvent
  | WsMessageRecallEvent
  | WsMessageDeleteEvent
  | WsReadSyncEvent
  | WsFriendRequestEvent
  | WsConversationUpdateEvent
  | { type: 'connected'; data: { user_id: number } }
  | { type: 'pong' }
  | { type: 'error'; message: string }