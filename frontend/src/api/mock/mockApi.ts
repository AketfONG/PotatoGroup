/**
 * 前端 mock 实现:与 real.ts 签名完全一致(satisfies typeof realApi)。
 * 数据来源:开发期 Vite 插件的 /__mock_db 中间件(读写 frontend/mock/db.json)。
 * 后端零感知;npm run dev:mock 时由 api/index.ts 切换到本实现。
 */

import { ApiError, getToken } from '../http'
import type {
  Conversation,
  ConversationItem,
  FriendItem,
  FriendRequest,
  FriendRequestListOut,
  HistoryOut,
  LoginOut,
  Member,
  Message,
  SyncItem,
  SyncOut,
  UserProfile,
  UserSearchOut,
  UserSummary,
} from '../types'

// ---------- db.json 结构 ----------

interface RawUser {
  user_id: number
  name: string
  password: string
  avatar: string | null
  email: string | null
  phone: string | null
  register_time: number
  login_time: number | null
}

interface RawFriendship {
  user_id: number
  friend_user_id: number
  remark: string | null
  group_name: string | null
}

interface RawFriendRequest {
  request_id: number
  from_user: number
  to_user_id: number
  status: 'pending' | 'accepted' | 'rejected'
  create_time: number
}

interface RawConversation {
  conversation_id: number
  name: string | null
  type: 'private' | 'group'
  avatar: string | null
  owner_id: number | null
  announcement: string | null
  create_time: number
  update_time: number
  member_ids: number[]
}

interface RawMessage {
  msg_id: number
  conversation_id: number
  sender_id: number | null
  body: string
  reply_to: number | null
  create_time: number
  recalled: boolean
}

interface RawMessageSeq {
  msg_id: number
  user_id: number
  seq: number
}

interface RawSyncEvent {
  seq: number
  kind: 'message' | 'recall' | 'read' | 'delete'
  user_id: number
  conversation_id: number
  data: Record<string, unknown> | null
}

interface Db {
  nextIds: { user: number; conversation: number; message: number; friendRequest: number; seq: number }
  users: RawUser[]
  friendships: RawFriendship[]
  friendRequests: RawFriendRequest[]
  conversations: RawConversation[]
  messages: RawMessage[]
  messageSeqs: RawMessageSeq[]
  deletedMsgs: { user_id: number; conversation_id: number; msg_id: number }[]
  readState: { user_id: number; conversation_id: number; last_read_msg_id: number }[]
  settings: { user_id: number; conversation_id: number; pinned: boolean; muted: boolean }[]
  seqs: { user_id: number; cursor: number }[]
  syncEvents: RawSyncEvent[]
  tokens: Record<string, number>
}

// ---------- 载入与持久化 ----------

let db: Db | null = null
let loading: Promise<void> | null = null
let persistTimer: number | null = null

async function ensureDb(): Promise<Db> {
  if (db) return db
  if (!loading) {
    loading = (async () => {
      const res = await fetch('/__mock_db')
      if (!res.ok) throw new ApiError(-1, 'mock db 加载失败')
      db = JSON.parse(String(await res.text())) as Db
    })()
  }
  await loading
  if (!db) throw new ApiError(-1, 'mock db 加载失败')
  return db
}

function persist(d: Db): void {
  if (persistTimer !== null) window.clearTimeout(persistTimer)
  persistTimer = window.setTimeout(() => {
    void fetch('/__mock_db', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(d),
    })
  }, 250)
}

// ---------- 工具 ----------

function auth(d: Db): number {
  const token = getToken()
  const userId = token ? d.tokens[token] : undefined
  if (userId === undefined) throw new ApiError(1002, '未登录或登录已过期')
  return userId
}

function summary(d: Db, userId: number): UserSummary {
  const u = d.users.find((x) => x.user_id === userId)
  if (!u) throw new ApiError(1004, '用户不存在')
  return { user_id: u.user_id, name: u.name, avatar: u.avatar, online: true }
}

function profile(d: Db, u: RawUser): UserProfile {
  return {
    user_id: u.user_id,
    name: u.name,
    avatar: u.avatar,
    email: u.email,
    phone: u.phone,
    register_time: u.register_time,
    login_time: u.login_time,
  }
}

function nextSeq(d: Db, userId: number): number {
  const row = d.seqs.find((s) => s.user_id === userId)
  const next = (row?.cursor ?? 0) + 1
  if (row) row.cursor = next
  else d.seqs.push({ user_id: userId, cursor: next })
  return next
}

function seqOf(d: Db, userId: number, msgId: number): number | undefined {
  return d.messageSeqs.find((m) => m.user_id === userId && m.msg_id === msgId)?.seq
}

function toMessage(d: Db, m: RawMessage, forUserId?: number): Message {
  return {
    msg_id: m.msg_id,
    conversation_id: m.conversation_id,
    sender_id: m.sender_id,
    body: m.recalled ? '[消息已撤回]' : m.body,
    reply_to: m.reply_to,
    create_time: m.create_time,
    ...(forUserId !== undefined ? { seq: seqOf(d, forUserId, m.msg_id) } : {}),
  }
}

function isDeletedForMe(d: Db, userId: number, conversationId: number, msgId: number): boolean {
  return d.deletedMsgs.some((x) => x.user_id === userId && x.conversation_id === conversationId && x.msg_id === msgId)
}

function lastReadMsgId(d: Db, userId: number, conversationId: number): number {
  return (
    d.readState.find((r) => r.user_id === userId && r.conversation_id === conversationId)?.last_read_msg_id ?? 0
  )
}

function toConversation(d: Db, c: RawConversation, forUserId?: number): Conversation {
  return {
    conversation_id: c.conversation_id,
    name: c.name,
    type: c.type,
    avatar: c.avatar,
    owner_id: c.owner_id,
    announcement: c.announcement,
    members: c.member_ids.map((id) => ({
      user: summary(d, id),
      role: c.owner_id === id ? ('owner' as const) : ('member' as const),
      join_time: c.create_time,
    })),
    create_time: c.create_time,
    update_time: c.update_time,
  }
}

function toItem(d: Db, c: RawConversation, me: number): ConversationItem {
  const msgs = d.messages
    .filter((m) => m.conversation_id === c.conversation_id && !isDeletedForMe(d, me, c.conversation_id, m.msg_id))
    .sort((a, b) => a.msg_id - b.msg_id)
  const last = msgs[msgs.length - 1] ?? null
  const read = lastReadMsgId(d, me, c.conversation_id)
  const unread = msgs.filter((m) => m.sender_id !== me && m.msg_id > read).length
  const setting = d.settings.find((s) => s.user_id === me && s.conversation_id === c.conversation_id)
  const other = c.type === 'private' ? c.member_ids.find((id) => id !== me) : undefined
  const name = c.type === 'group' ? c.name : (other !== undefined ? (d.users.find((u) => u.user_id === other)?.name ?? null) : null)
  return {
    conversation_id: c.conversation_id,
    name,
    type: c.type,
    avatar: c.avatar,
    member_count: c.member_ids.length,
    last_msg: last ? toMessage(d, last, me) : null,
    unread_count: unread,
    pinned: setting?.pinned ?? false,
    muted: setting?.muted ?? false,
    update_time: c.update_time,
  }
}

function pushMessageEvents(d: Db, c: RawConversation, m: RawMessage): void {
  // 写扩散:给每个成员的用户链写一条 message 事件并分配 seq
  for (const memberId of c.member_ids) {
    const seq = nextSeq(d, memberId)
    d.syncEvents.push({
      seq,
      kind: 'message',
      user_id: memberId,
      conversation_id: c.conversation_id,
      data: toMessage(d, m, memberId) as unknown as Record<string, unknown>,
    })
  }
}

function myConversation(d: Db, conversationId: number, me: number): RawConversation {
  const c = d.conversations.find((x) => x.conversation_id === conversationId)
  if (!c) throw new ApiError(1004, '会话不存在')
  if (!c.member_ids.includes(me)) throw new ApiError(1003, '无权限访问该会话')
  return c
}

function requireAdmin(d: Db, c: RawConversation, me: number): void {
  if (c.type !== 'group') throw new ApiError(1003, '单聊会话不支持该操作')
  if (c.owner_id !== me) throw new ApiError(1003, '仅群主可执行该操作')
}

// ---------- 实现 ----------

export const mockApi = {
  // ---------- 认证 ----------

  async register(name: string, password: string): Promise<{ user_id: number }> {
    const d = await ensureDb()
    const trimmed = name.trim()
    if (!trimmed || !password) throw new ApiError(1001, '用户名或密码不能为空')
    if (d.users.some((u) => u.name === trimmed)) throw new ApiError(2001, '用户名已存在')
    const user: RawUser = {
      user_id: d.nextIds.user++,
      name: trimmed,
      password,
      avatar: null,
      email: null,
      phone: null,
      register_time: Math.floor(Date.now() / 1000),
      login_time: null,
    }
    d.users.push(user)
    persist(d)
    return { user_id: user.user_id }
  },

  async login(name: string, password: string): Promise<LoginOut> {
    const d = await ensureDb()
    const u = d.users.find((x) => x.name === name.trim())
    if (!u || u.password !== password) throw new ApiError(1002, '用户名或密码错误')
    const token = `mock-token-${u.user_id}-${Date.now()}`
    d.tokens[token] = u.user_id
    u.login_time = Math.floor(Date.now() / 1000)
    persist(d)
    return { token, user: summary(d, u.user_id) }
  },

  async logout(): Promise<void> {
    const d = await ensureDb()
    const token = getToken()
    if (token) delete d.tokens[token]
    persist(d)
  },

  // ---------- 用户 ----------

  async myProfile(): Promise<UserProfile> {
    const d = await ensureDb()
    const me = auth(d)
    const u = d.users.find((x) => x.user_id === me)
    if (!u) throw new ApiError(1004, '用户不存在')
    return profile(d, u)
  },

  async updateProfile(payload: {
    name?: string
    avatar?: string | null
    email?: string | null
    phone?: string | null
    old_password?: string
    new_password?: string
  }): Promise<UserProfile> {
    const d = await ensureDb()
    const me = auth(d)
    const u = d.users.find((x) => x.user_id === me)
    if (!u) throw new ApiError(1004, '用户不存在')
    if (payload.name !== undefined) {
      const trimmed = payload.name.trim()
      if (!trimmed) throw new ApiError(1001, '用户名不能为空')
      if (d.users.some((x) => x.user_id !== me && x.name === trimmed)) throw new ApiError(2001, '用户名已存在')
      u.name = trimmed
    }
    if (payload.avatar !== undefined) u.avatar = payload.avatar
    if (payload.email !== undefined) u.email = payload.email
    if (payload.phone !== undefined) u.phone = payload.phone
    if (payload.new_password) {
      if (!payload.old_password || payload.old_password !== u.password) {
        throw new ApiError(1001, '原密码不正确')
      }
      u.password = payload.new_password
    }
    persist(d)
    return profile(d, u)
  },

  async deleteAccount(): Promise<void> {
    const d = await ensureDb()
    const me = auth(d)
    d.users = d.users.filter((u) => u.user_id !== me)
    d.friendships = d.friendships.filter((f) => f.user_id !== me && f.friend_user_id !== me)
    d.friendRequests = d.friendRequests.filter((r) => r.from_user !== me && r.to_user_id !== me)
    for (const c of d.conversations) {
      c.member_ids = c.member_ids.filter((id) => id !== me)
    }
    for (const m of d.messages) {
      if (m.sender_id === me) m.sender_id = null
    }
    for (const [token, uid] of Object.entries(d.tokens)) {
      if (uid === me) delete d.tokens[token]
    }
    persist(d)
  },

  async getUser(userId: number): Promise<UserSummary> {
    const d = await ensureDb()
    return summary(d, userId)
  },

  async searchUsers(keyword: string): Promise<UserSearchOut> {
    const d = await ensureDb()
    const me = auth(d)
    const kw = keyword.trim().toLowerCase()
    return {
      items: d.users
        .filter((u) => u.user_id !== me && (!kw || u.name.toLowerCase().includes(kw)))
        .map((u) => summary(d, u.user_id)),
    }
  },

  // ---------- 好友 ----------

  async listFriends(): Promise<{ items: FriendItem[] }> {
    const d = await ensureDb()
    const me = auth(d)
    const items: FriendItem[] = []
    for (const f of d.friendships.filter((x) => x.user_id === me)) {
      const u = d.users.find((x) => x.user_id === f.friend_user_id)
      if (!u) continue
      items.push({
        user_id: u.user_id,
        name: u.name,
        avatar: u.avatar,
        remark: f.remark,
        group_name: f.group_name,
        online: true,
      })
    }
    return { items }
  },

  async deleteFriend(friendUserId: number): Promise<void> {
    const d = await ensureDb()
    const me = auth(d)
    const before = d.friendships.length
    d.friendships = d.friendships.filter(
      (f) => !((f.user_id === me && f.friend_user_id === friendUserId) || (f.user_id === friendUserId && f.friend_user_id === me)),
    )
    if (d.friendships.length === before) throw new ApiError(1004, '该好友不存在')
    persist(d)
  },

  async createFriendRequest(targetUserId: number): Promise<{ request_id: number }> {
    const d = await ensureDb()
    const me = auth(d)
    if (targetUserId === me) throw new ApiError(1001, '不能添加自己为好友')
    const target = d.users.find((u) => u.user_id === targetUserId)
    if (!target) throw new ApiError(1004, '用户不存在')
    const isFriend = d.friendships.some((f) => f.user_id === me && f.friend_user_id === targetUserId)
    if (isFriend) throw new ApiError(2002, '已经是好友了')
    const dup = d.friendRequests.some(
      (r) =>
        r.status === 'pending' &&
        ((r.from_user === me && r.to_user_id === targetUserId) || (r.from_user === targetUserId && r.to_user_id === me)),
    )
    if (dup) throw new ApiError(2002, '已存在待处理的好友申请')
    const request: RawFriendRequest = {
      request_id: d.nextIds.friendRequest++,
      from_user: me,
      to_user_id: targetUserId,
      status: 'pending',
      create_time: Math.floor(Date.now() / 1000),
    }
    d.friendRequests.push(request)
    persist(d)
    return { request_id: request.request_id }
  },

  async listFriendRequests(): Promise<FriendRequestListOut> {
    const d = await ensureDb()
    const me = auth(d)
    const items: FriendRequest[] = d.friendRequests
      .filter((r) => r.to_user_id === me)
      .map((r) => ({
        request_id: r.request_id,
        from_user: d.users.some((u) => u.user_id === r.from_user) ? summary(d, r.from_user) : null,
        to_user_id: r.to_user_id,
        status: r.status,
        create_time: r.create_time,
      }))
    return { items }
  },

  async acceptFriendRequest(requestId: number): Promise<void> {
    const d = await ensureDb()
    const me = auth(d)
    const r = d.friendRequests.find((x) => x.request_id === requestId)
    if (!r || r.to_user_id !== me) throw new ApiError(1004, '好友申请不存在')
    if (r.status !== 'pending') throw new ApiError(2002, '该申请已处理')
    r.status = 'accepted'
    d.friendships.push({ user_id: me, friend_user_id: r.from_user, remark: null, group_name: null })
    d.friendships.push({ user_id: r.from_user, friend_user_id: me, remark: null, group_name: null })
    persist(d)
  },

  async rejectFriendRequest(requestId: number): Promise<void> {
    const d = await ensureDb()
    const me = auth(d)
    const r = d.friendRequests.find((x) => x.request_id === requestId)
    if (!r || r.to_user_id !== me) throw new ApiError(1004, '好友申请不存在')
    if (r.status !== 'pending') throw new ApiError(2002, '该申请已处理')
    r.status = 'rejected'
    persist(d)
  },

  // ---------- 会话 ----------

  async listConversations(): Promise<{ items: ConversationItem[] }> {
    const d = await ensureDb()
    const me = auth(d)
    const items = d.conversations
      .filter((c) => c.member_ids.includes(me))
      .map((c) => toItem(d, c, me))
      .sort((a, b) => b.update_time - a.update_time)
    return { items }
  },

  async createGroup(name: string, memberIds: number[]): Promise<Conversation> {
    const d = await ensureDb()
    const me = auth(d)
    const trimmed = name.trim()
    if (!trimmed) throw new ApiError(1001, '群名不能为空')
    for (const id of memberIds) {
      if (!d.users.some((u) => u.user_id === id)) throw new ApiError(1004, '成员不存在')
    }
    const myGroups = d.conversations.filter((c) => c.type === 'group' && c.member_ids.includes(me))
    if (myGroups.some((c) => c.name === trimmed)) throw new ApiError(2003, '已存在同名群聊')
    const memberIdsUnique = [...new Set([me, ...memberIds])]
    const conv: RawConversation = {
      conversation_id: d.nextIds.conversation++,
      name: trimmed,
      type: 'group',
      avatar: null,
      owner_id: me,
      announcement: null,
      create_time: Math.floor(Date.now() / 1000),
      update_time: Math.floor(Date.now() / 1000),
      member_ids: memberIdsUnique,
    }
    d.conversations.push(conv)
    persist(d)
    return toConversation(d, conv, me)
  },

  async createPrivateChat(targetUserId: number): Promise<Conversation> {
    const d = await ensureDb()
    const me = auth(d)
    if (targetUserId === me) throw new ApiError(1001, '不能与自己发起会话')
    if (!d.users.some((u) => u.user_id === targetUserId)) throw new ApiError(1004, '用户不存在')
    const existing = d.conversations.find(
      (c) => c.type === 'private' && c.member_ids.length === 2 && c.member_ids.includes(me) && c.member_ids.includes(targetUserId),
    )
    if (existing) return toConversation(d, existing, me)
    const conv: RawConversation = {
      conversation_id: d.nextIds.conversation++,
      name: null,
      type: 'private',
      avatar: null,
      owner_id: null,
      announcement: null,
      create_time: Math.floor(Date.now() / 1000),
      update_time: Math.floor(Date.now() / 1000),
      member_ids: [me, targetUserId],
    }
    d.conversations.push(conv)
    persist(d)
    return toConversation(d, conv, me)
  },

  async conversationDetail(conversationId: number): Promise<Conversation> {
    const d = await ensureDb()
    const me = auth(d)
    return toConversation(d, myConversation(d, conversationId, me), me)
  },

  async updateConversation(
    conversationId: number,
    payload: { name?: string; announcement?: string },
  ): Promise<Conversation> {
    const d = await ensureDb()
    const me = auth(d)
    const c = myConversation(d, conversationId, me)
    requireAdmin(d, c, me)
    if (payload.name !== undefined) {
      const trimmed = payload.name.trim()
      if (!trimmed) throw new ApiError(1001, '群名不能为空')
      c.name = trimmed
    }
    if (payload.announcement !== undefined) c.announcement = payload.announcement
    c.update_time = Math.floor(Date.now() / 1000)
    persist(d)
    return toConversation(d, c, me)
  },

  async addMembers(conversationId: number, userIds: number[]): Promise<{ items: Member[] }> {
    const d = await ensureDb()
    const me = auth(d)
    const c = myConversation(d, conversationId, me)
    requireAdmin(d, c, me)
    const added: Member[] = []
    for (const id of userIds) {
      if (!d.users.some((u) => u.user_id === id)) throw new ApiError(1004, '成员不存在')
      if (c.member_ids.includes(id)) throw new ApiError(2003, '该用户已在群中')
      c.member_ids.push(id)
      added.push({ user: summary(d, id), role: 'member', join_time: Math.floor(Date.now() / 1000) })
    }
    c.update_time = Math.floor(Date.now() / 1000)
    persist(d)
    return { items: added }
  },

  async removeMember(conversationId: number, userId: number): Promise<void> {
    const d = await ensureDb()
    const me = auth(d)
    const c = myConversation(d, conversationId, me)
    requireAdmin(d, c, me)
    if (!c.member_ids.includes(userId)) throw new ApiError(1004, '该成员不在群中')
    c.member_ids = c.member_ids.filter((id) => id !== userId)
    c.update_time = Math.floor(Date.now() / 1000)
    persist(d)
  },

  async leaveConversation(conversationId: number): Promise<void> {
    const d = await ensureDb()
    const me = auth(d)
    const c = myConversation(d, conversationId, me)
    c.member_ids = c.member_ids.filter((id) => id !== me)
    if (c.owner_id === me) c.owner_id = c.member_ids[0] ?? null
    c.update_time = Math.floor(Date.now() / 1000)
    persist(d)
  },

  async updateMyConversationSettings(
    conversationId: number,
    settings: { pinned?: boolean; muted?: boolean },
  ): Promise<void> {
    const d = await ensureDb()
    const me = auth(d)
    myConversation(d, conversationId, me)
    const row = d.settings.find((s) => s.user_id === me && s.conversation_id === conversationId)
    if (row) {
      if (settings.pinned !== undefined) row.pinned = settings.pinned
      if (settings.muted !== undefined) row.muted = settings.muted
    } else {
      d.settings.push({
        user_id: me,
        conversation_id: conversationId,
        pinned: settings.pinned ?? false,
        muted: settings.muted ?? false,
      })
    }
    persist(d)
  },

  async markRead(conversationId: number, readIndex: number): Promise<void> {
    const d = await ensureDb()
    const me = auth(d)
    const c = myConversation(d, conversationId, me)
    // readIndex 是我的用户链 seq:换算成 msg_id 落库
    const row = d.messageSeqs.find((m) => m.user_id === me && m.seq === readIndex)
    if (!row) throw new ApiError(1001, 'read_index 无效')
    const read = d.readState.find((r) => r.user_id === me && r.conversation_id === conversationId)
    if (read) read.last_read_msg_id = Math.max(read.last_read_msg_id, row.msg_id)
    else d.readState.push({ user_id: me, conversation_id: conversationId, last_read_msg_id: row.msg_id })
    // 多设备同步:给自己链上写一条 read 事件
    d.syncEvents.push({
      seq: nextSeq(d, me),
      kind: 'read',
      user_id: me,
      conversation_id: c.conversation_id,
      data: { conversation_id: c.conversation_id },
    })
    persist(d)
  },

  // ---------- 消息与同步 ----------

  async sendMessage(conversationId: number, body: string, replyTo: number | null = null): Promise<Message> {
    const d = await ensureDb()
    const me = auth(d)
    const c = myConversation(d, conversationId, me)
    const trimmed = body.trim()
    if (!trimmed) throw new ApiError(1001, '消息内容不能为空')
    const m: RawMessage = {
      msg_id: d.nextIds.message++,
      conversation_id: c.conversation_id,
      sender_id: me,
      body: trimmed,
      reply_to: replyTo,
      create_time: Math.floor(Date.now() / 1000),
      recalled: false,
    }
    d.messages.push(m)
    c.update_time = m.create_time
    pushMessageEvents(d, c, m)
    persist(d)
    return toMessage(d, m, me)
  },

  async conversationHistory(
    conversationId: number,
    cursor?: number | null,
    filters: { sender_id?: number; start_time?: number; end_time?: number } = {},
  ): Promise<HistoryOut> {
    const d = await ensureDb()
    const me = auth(d)
    myConversation(d, conversationId, me)
    const all = d.messages
      .filter(
        (m) =>
          m.conversation_id === conversationId &&
          !isDeletedForMe(d, me, conversationId, m.msg_id) &&
          (cursor === undefined || cursor === null || m.msg_id < cursor) &&
          (filters.sender_id === undefined || m.sender_id === filters.sender_id) &&
          (filters.start_time === undefined || m.create_time >= filters.start_time) &&
          (filters.end_time === undefined || m.create_time <= filters.end_time),
      )
      .sort((a, b) => b.msg_id - a.msg_id) // 新的在前,与后端一致
    const page = all.slice(0, 50)
    const nextCursor = all.length > page.length ? (page[page.length - 1]?.msg_id ?? null) : null
    return { items: page.map((m) => toMessage(d, m, me)), next_cursor: nextCursor }
  },

  async recallMessage(conversationId: number, msgId: number): Promise<void> {
    const d = await ensureDb()
    const me = auth(d)
    const c = myConversation(d, conversationId, me)
    const m = d.messages.find((x) => x.conversation_id === conversationId && x.msg_id === msgId)
    if (!m) throw new ApiError(1004, '消息不存在')
    if (m.sender_id !== me) throw new ApiError(1003, '只能撤回自己的消息')
    if (m.recalled) return
    m.recalled = true
    for (const memberId of c.member_ids) {
      d.syncEvents.push({
        seq: nextSeq(d, memberId),
        kind: 'recall',
        user_id: memberId,
        conversation_id: c.conversation_id,
        data: { msg_id: m.msg_id, conversation_id: c.conversation_id },
      })
    }
    persist(d)
  },

  async deleteMessage(conversationId: number, msgId: number): Promise<void> {
    const d = await ensureDb()
    const me = auth(d)
    const c = myConversation(d, conversationId, me)
    const m = d.messages.find((x) => x.conversation_id === conversationId && x.msg_id === msgId)
    if (!m) throw new ApiError(1004, '消息不存在')
    if (isDeletedForMe(d, me, conversationId, msgId)) return
    d.deletedMsgs.push({ user_id: me, conversation_id: c.conversation_id, msg_id: msgId })
    // 本地删除只影响我自己(含我的其他设备)
    d.syncEvents.push({
      seq: nextSeq(d, me),
      kind: 'delete',
      user_id: me,
      conversation_id: c.conversation_id,
      data: { msg_id: m.msg_id, conversation_id: c.conversation_id },
    })
    persist(d)
  },

  async sync(cursor: number): Promise<SyncOut> {
    const d = await ensureDb()
    const me = auth(d)
    const mine = d.syncEvents.filter((e) => e.user_id === me && e.seq > cursor).sort((a, b) => a.seq - b.seq)
    const page = mine.slice(0, 200)
    const nextCursor = mine.length > page.length ? page[page.length - 1].seq : null
    const items: SyncItem[] = page.map((e) => ({
      seq: e.seq,
      kind: e.kind,
      conversation_id: e.conversation_id,
      data: e.data,
    }))
    return { items, next_cursor: nextCursor }
  },
}
