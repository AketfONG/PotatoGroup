/**
 * 聊天 store:会话列表、当前会话消息、未读、置顶/免打扰、WS + /sync 合并。
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import * as api from '@/api'
import { wsClient } from '@/api/ws'
import type { Conversation, ConversationItem, Message, SyncItem, WsEvent } from '@/api/types'
import { useFriendsStore } from './friends'
import { useUserStore } from './user'

export const useChatStore = defineStore('chat', () => {
  const userStore = useUserStore()

  const conversations = ref<ConversationItem[]>([])
  const activeId = ref<number | null>(null)
  const messagesByConversation = ref<Record<number, Message[]>>({})
  /** 历史翻页:conversation_id → next_cursor */
  const historyCursor = ref<Record<number, number | null>>({})
  const loadingOlder = ref(false)
  const replyTo = ref<Message | null>(null)
  const groupDetail = ref<Conversation | null>(null)

  const sortedConversations = computed(() => {
    return [...conversations.value].sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
      return b.update_time - a.update_time
    })
  })

  const activeConversation = computed(
    () => conversations.value.find((c) => c.conversation_id === activeId.value) ?? null,
  )
  const activeMessages = computed(() => messagesByConversation.value[activeId.value ?? -1] ?? [])
  const hasMoreHistory = computed(() => {
    if (activeId.value === null) return false
    const c = historyCursor.value[activeId.value]
    return c !== null && c !== undefined
  })

  async function loadConversations(): Promise<void> {
    const out = await api.listConversations()
    conversations.value = out.items
  }

  async function loadHistory(conversationId: number, reset = true): Promise<void> {
    if (reset) {
      const out = await api.conversationHistory(conversationId)
      const list = [...out.items].reverse()
      messagesByConversation.value[conversationId] = mergeMessages([], list)
      historyCursor.value[conversationId] = out.next_cursor
    }
  }

  async function loadOlderHistory(): Promise<void> {
    if (activeId.value === null || loadingOlder.value) return
    const cursor = historyCursor.value[activeId.value]
    if (cursor === null || cursor === undefined) return
    loadingOlder.value = true
    try {
      const out = await api.conversationHistory(activeId.value, cursor)
      const older = [...out.items].reverse()
      messagesByConversation.value[activeId.value] = mergeMessages(
        messagesByConversation.value[activeId.value] ?? [],
        older,
      )
      historyCursor.value[activeId.value] = out.next_cursor
    } finally {
      loadingOlder.value = false
    }
  }

  async function openConversation(conversationId: number): Promise<void> {
    activeId.value = conversationId
    replyTo.value = null
    groupDetail.value = null
    await loadHistory(conversationId, true)
    await clearUnread(conversationId)
    const conv = conversations.value.find((c) => c.conversation_id === conversationId)
    if (conv?.type === 'group') {
      try {
        groupDetail.value = await api.conversationDetail(conversationId)
      } catch {
        groupDetail.value = null
      }
    }
  }

  /** 窄屏返回会话列表 */
  function clearActiveConversation(): void {
    activeId.value = null
    replyTo.value = null
    groupDetail.value = null
  }

  async function sendMessage(body: string): Promise<void> {
    if (!activeId.value || !body.trim()) return
    const replyId = replyTo.value?.msg_id ?? null
    const sent = await api.sendMessage(activeId.value, body.trim(), replyId)
    upsertMessage(sent)
    bumpConversationPreview(sent)
    replyTo.value = null
  }

  function setReplyTo(msg: Message | null): void {
    replyTo.value = msg
  }

  async function recallMessage(msg: Message): Promise<void> {
    await api.recallMessage(msg.conversation_id, msg.msg_id)
    const list = messagesByConversation.value[msg.conversation_id] ?? []
    const target = list.find((m) => m.msg_id === msg.msg_id)
    if (target) target.body = '[消息已撤回]'
  }

  async function deleteMessage(conversationId: number, msgId: number): Promise<void> {
    await api.deleteMessage(conversationId, msgId)
    removeMessage(conversationId, msgId)
  }

  async function clearUnread(conversationId: number): Promise<void> {
    const msgs = messagesByConversation.value[conversationId] ?? []
    const latest = msgs[msgs.length - 1]
    if (!latest || latest.seq === undefined) return
    await api.markRead(conversationId, latest.seq)
    const conv = conversations.value.find((c) => c.conversation_id === conversationId)
    if (conv) conv.unread_count = 0
  }

  async function setPinned(conversationId: number, pinned: boolean): Promise<void> {
    await api.updateMyConversationSettings(conversationId, { pinned })
    const conv = conversations.value.find((c) => c.conversation_id === conversationId)
    if (conv) conv.pinned = pinned
  }

  async function setMuted(conversationId: number, muted: boolean): Promise<void> {
    await api.updateMyConversationSettings(conversationId, { muted })
    const conv = conversations.value.find((c) => c.conversation_id === conversationId)
    if (conv) conv.muted = muted
  }

  async function createGroup(name: string, memberIds: number[]): Promise<Conversation> {
    const conv = await api.createGroup(name, memberIds)
    await loadConversations()
    await openConversation(conv.conversation_id)
    return conv
  }

  async function startPrivateChat(targetUserId: number): Promise<void> {
    const conv = await api.createPrivateChat(targetUserId)
    await loadConversations()
    await openConversation(conv.conversation_id)
  }

  async function refreshGroupDetail(): Promise<void> {
    if (activeId.value === null) return
    groupDetail.value = await api.conversationDetail(activeId.value)
    await loadConversations()
  }

  async function updateGroupInfo(payload: { name?: string; announcement?: string }): Promise<void> {
    if (activeId.value === null) return
    groupDetail.value = await api.updateConversation(activeId.value, payload)
    await loadConversations()
  }

  async function inviteMembers(userIds: number[]): Promise<void> {
    if (activeId.value === null) return
    await api.addMembers(activeId.value, userIds)
    await refreshGroupDetail()
  }

  async function kickMember(userId: number): Promise<void> {
    if (activeId.value === null) return
    await api.removeMember(activeId.value, userId)
    await refreshGroupDetail()
  }

  async function leaveGroup(): Promise<void> {
    if (activeId.value === null) return
    const id = activeId.value
    await api.leaveConversation(id)
    activeId.value = null
    groupDetail.value = null
    delete messagesByConversation.value[id]
    await loadConversations()
  }

  /** 定位到某条消息:若未加载则向前翻页补齐 */
  async function locateMessage(msgId: number): Promise<'ok' | 'missing'> {
    if (activeId.value === null) return 'missing'
    const cid = activeId.value
    for (let i = 0; i < 20; i++) {
      const list = messagesByConversation.value[cid] ?? []
      if (list.some((m) => m.msg_id === msgId)) return 'ok'
      if (!historyCursor.value[cid]) break
      await loadOlderHistory()
    }
    return 'missing'
  }

  function findMessage(conversationId: number, msgId: number): Message | undefined {
    return (messagesByConversation.value[conversationId] ?? []).find((m) => m.msg_id === msgId)
  }

  // ---------- sync 合并 ----------

  function applySyncItems(items: SyncItem[]): void {
    for (const item of items) {
      if (item.kind === 'message' && item.data) {
        upsertMessage(item.data as unknown as Message)
      } else if (item.kind === 'recall' && item.data) {
        const payload = item.data as { msg_id?: number; conversation_id?: number }
        if (payload.msg_id !== undefined && payload.conversation_id !== undefined) {
          const list = messagesByConversation.value[payload.conversation_id] ?? []
          const target = list.find((m) => m.msg_id === payload.msg_id)
          if (target) target.body = '[消息已撤回]'
        }
      } else if (item.kind === 'delete' && item.data) {
        const payload = item.data as { msg_id?: number; conversation_id?: number }
        if (payload.msg_id !== undefined && payload.conversation_id !== undefined) {
          removeMessage(payload.conversation_id, payload.msg_id)
        }
      } else if (item.kind === 'read' && item.data) {
        const payload = item.data as { conversation_id?: number }
        if (payload.conversation_id !== undefined) {
          const conv = conversations.value.find((c) => c.conversation_id === payload.conversation_id)
          if (conv) conv.unread_count = 0
        }
      }
      if (item.seq > wsClient.localSeq) wsClient.localSeq = item.seq
    }
  }

  async function pullAndApplySync(): Promise<void> {
    const out = await wsClient.resync()
    applySyncItems(out.items)
    let cursor = out.next_cursor
    while (cursor !== null) {
      const more = await api.sync(cursor)
      applySyncItems(more.items)
      cursor = more.next_cursor
    }
    await loadConversations()
  }

  // ---------- WS ----------

  async function handleEvent(event: WsEvent): Promise<void> {
    switch (event.type) {
      case 'message.new': {
        const msg = event.data
        upsertMessage(msg)
        bumpConversationPreview(msg)
        const conv = conversations.value.find((c) => c.conversation_id === msg.conversation_id)
        if (conv && msg.sender_id !== userStore.user?.user_id) {
          if (conv.conversation_id === activeId.value) await clearUnread(conv.conversation_id)
          else if (!conv.muted) conv.unread_count += 1
          else conv.unread_count += 1
        }
        break
      }
      case 'message.recall': {
        const { msg_id, conversation_id } = event.data
        const list = messagesByConversation.value[conversation_id] ?? []
        const target = list.find((m) => m.msg_id === msg_id)
        if (target) target.body = '[消息已撤回]'
        break
      }
      case 'message.delete': {
        const { msg_id, conversation_id } = event.data
        removeMessage(conversation_id, msg_id)
        break
      }
      case 'read.sync': {
        const conv = conversations.value.find((c) => c.conversation_id === event.data.conversation_id)
        if (conv) conv.unread_count = 0
        break
      }
      case 'conversation.update': {
        await loadConversations()
        if (activeId.value === event.data.conversation_id) {
          groupDetail.value = event.data
        }
        break
      }
      case 'friend.request': {
        try {
          await useFriendsStore().loadRequests()
        } catch {
          /* 好友页未挂载时忽略 */
        }
        break
      }
    }
  }

  function bumpConversationPreview(msg: Message): void {
    const conv = conversations.value.find((c) => c.conversation_id === msg.conversation_id)
    if (conv) {
      conv.last_msg = msg
      conv.update_time = msg.create_time
    }
  }

  function upsertMessage(msg: Message): void {
    const list = messagesByConversation.value[msg.conversation_id] ?? []
    if (!list.some((m) => m.msg_id === msg.msg_id)) {
      list.push(msg)
      list.sort((a, b) => a.msg_id - b.msg_id)
    } else {
      const idx = list.findIndex((m) => m.msg_id === msg.msg_id)
      if (idx >= 0) list[idx] = { ...list[idx], ...msg }
    }
    messagesByConversation.value[msg.conversation_id] = list
  }

  function mergeMessages(existing: Message[], incoming: Message[]): Message[] {
    const map = new Map(existing.map((m) => [m.msg_id, m]))
    for (const m of incoming) map.set(m.msg_id, m)
    return [...map.values()].sort((a, b) => a.msg_id - b.msg_id)
  }

  function removeMessage(conversationId: number, msgId: number): void {
    const list = messagesByConversation.value[conversationId]
    if (!list) return
    messagesByConversation.value[conversationId] = list.filter((m) => m.msg_id !== msgId)
  }

  let offWs: (() => void) | null = null
  let offResync: (() => void) | null = null

  async function startSession(): Promise<void> {
    await loadConversations()
    const initial = await wsClient.initialSync()
    applySyncItems(initial.items)
    offWs?.()
    offResync?.()
    offWs = wsClient.on((ev) => {
      void handleEvent(ev)
    })
    offResync = wsClient.onResync((out) => {
      applySyncItems(out.items)
      void loadConversations()
    })
    wsClient.connect()
  }

  function endSession(): void {
    offWs?.()
    offResync?.()
    offWs = null
    offResync = null
    wsClient.disconnect()
    conversations.value = []
    messagesByConversation.value = {}
    historyCursor.value = {}
    activeId.value = null
    replyTo.value = null
    groupDetail.value = null
  }

  return {
    conversations,
    sortedConversations,
    activeId,
    activeConversation,
    activeMessages,
    hasMoreHistory,
    loadingOlder,
    replyTo,
    groupDetail,
    loadConversations,
    openConversation,
    clearActiveConversation,
    loadOlderHistory,
    sendMessage,
    setReplyTo,
    recallMessage,
    deleteMessage,
    clearUnread,
    setPinned,
    setMuted,
    createGroup,
    startPrivateChat,
    refreshGroupDetail,
    updateGroupInfo,
    inviteMembers,
    kickMember,
    leaveGroup,
    locateMessage,
    findMessage,
    pullAndApplySync,
    handleEvent,
    startSession,
    endSession,
  }
})
