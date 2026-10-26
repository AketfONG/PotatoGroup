/**
 * 真实后端 API 实现(经 Vite 代理访问 FastAPI)。
 * 契约见 docs/02-API约定.md;由 api/index.ts 按模式统一分发。
 */

import { http, unwrap } from './http'
import type {
  Conversation,
  ConversationItem,
  FriendListOut,
  FriendRequestListOut,
  HistoryOut,
  LoginOut,
  Member,
  Message,
  SyncOut,
  UserProfile,
  UserSearchOut,
  UserSummary,
} from './types'

// ---------- 认证 ----------

export async function register(name: string, password: string): Promise<{ user_id: number }> {
  return unwrap<{ user_id: number }>(http.post('/auth/register', { name, password }))
}

export async function login(name: string, password: string): Promise<LoginOut> {
  return unwrap<LoginOut>(http.post('/auth/login', { name, password }))
}

export async function logout(): Promise<void> {
  await unwrap(http.delete('/auth/logout'))
}

// ---------- 用户 ----------

export async function myProfile(): Promise<UserProfile> {
  return unwrap<UserProfile>(http.get('/users/me'))
}

export async function updateProfile(payload: {
  name?: string
  avatar?: string | null
  email?: string | null
  phone?: string | null
  old_password?: string
  new_password?: string
}): Promise<UserProfile> {
  return unwrap<UserProfile>(http.patch('/users/me', payload))
}

export async function deleteAccount(): Promise<void> {
  await unwrap(http.delete('/users/me'))
}

export async function getUser(userId: number): Promise<UserSummary> {
  return unwrap<UserSummary>(http.get(`/users/${userId}`))
}

export async function searchUsers(keyword: string): Promise<UserSearchOut> {
  return unwrap<UserSearchOut>(http.get('/users', { params: { keyword } }))
}

// ---------- 好友 ----------

export async function listFriends(): Promise<FriendListOut> {
  return unwrap<FriendListOut>(http.get('/friends'))
}

export async function deleteFriend(friendUserId: number): Promise<void> {
  await unwrap(http.delete(`/friends/${friendUserId}`))
}

export async function createFriendRequest(targetUserId: number): Promise<{ request_id: number }> {
  return unwrap<{ request_id: number }>(http.post('/friend-requests', { target_user_id: targetUserId }))
}

export async function listFriendRequests(): Promise<FriendRequestListOut> {
  return unwrap<FriendRequestListOut>(http.get('/friend-requests'))
}

export async function acceptFriendRequest(requestId: number): Promise<void> {
  await unwrap(http.post(`/friend-requests/${requestId}/accept`))
}

export async function rejectFriendRequest(requestId: number): Promise<void> {
  await unwrap(http.post(`/friend-requests/${requestId}/reject`))
}

// ---------- 会话 ----------

export async function listConversations(): Promise<{ items: ConversationItem[] }> {
  return unwrap<{ items: ConversationItem[] }>(http.get('/conversations'))
}

export async function createGroup(name: string, memberIds: number[]): Promise<Conversation> {
  return unwrap<Conversation>(http.post('/conversations', { name, member_ids: memberIds }))
}

export async function createPrivateChat(targetUserId: number): Promise<Conversation> {
  return unwrap<Conversation>(http.post('/conversations/private', { target_user_id: targetUserId }))
}

export async function conversationDetail(conversationId: number): Promise<Conversation> {
  return unwrap<Conversation>(http.get(`/conversations/${conversationId}`))
}

export async function updateConversation(
  conversationId: number,
  payload: { name?: string; announcement?: string },
): Promise<Conversation> {
  return unwrap<Conversation>(http.patch(`/conversations/${conversationId}`, payload))
}

export async function addMembers(conversationId: number, userIds: number[]): Promise<{ items: Member[] }> {
  return unwrap<{ items: Member[] }>(
    http.post(`/conversations/${conversationId}/members`, { user_ids: userIds }),
  )
}

export async function removeMember(conversationId: number, userId: number): Promise<void> {
  await unwrap(http.delete(`/conversations/${conversationId}/members/${userId}`))
}

export async function leaveConversation(conversationId: number): Promise<void> {
  await unwrap(http.post(`/conversations/${conversationId}/members/me`))
}

export async function updateMyConversationSettings(
  conversationId: number,
  settings: { pinned?: boolean; muted?: boolean },
): Promise<void> {
  await unwrap(http.patch(`/conversations/${conversationId}/me`, settings))
}

export async function markRead(conversationId: number, readIndex: number): Promise<void> {
  await unwrap(http.post(`/conversations/${conversationId}/read`, { read_index: readIndex }))
}

// ---------- 消息与同步 ----------

export async function sendMessage(conversationId: number, body: string, replyTo: number | null = null): Promise<Message> {
  return unwrap<Message>(http.post(`/conversations/${conversationId}/messages`, { body, reply_to: replyTo }))
}

export async function conversationHistory(
  conversationId: number,
  cursor?: number | null,
  filters: { sender_id?: number; start_time?: number; end_time?: number } = {},
): Promise<HistoryOut> {
  return unwrap<HistoryOut>(
    http.get(`/conversations/${conversationId}/messages`, {
      params: { cursor: cursor ?? undefined, limit: 50, ...filters },
    }),
  )
}

export async function recallMessage(conversationId: number, msgId: number): Promise<void> {
  await unwrap(http.post(`/conversations/${conversationId}/messages/${msgId}/recall`))
}

/** 本地删除:只对我生效(服务端写 `kind="delete"` 墓碑),其他成员不受影响 */
export async function deleteMessage(conversationId: number, msgId: number): Promise<void> {
  await unwrap(http.delete(`/conversations/${conversationId}/messages/${msgId}`))
}

export async function sync(cursor: number): Promise<SyncOut> {
  return unwrap<SyncOut>(http.get('/sync', { params: { cursor, limit: 200 } }))
}
