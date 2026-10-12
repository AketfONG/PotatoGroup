/**
 * 聊天 store:会话列表、当前会话消息、未读数、WS 事件消费。
 *
 * 消息完整性:WS 推送 + /sync 兜底双保险(见 docs/02-API约定.md 第 7 节),
 * 本 store 维护去重(msg_id)与会话归组。
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import * as api from '@/api'
import { wsClient } from '@/api/ws'
import type { ConversationItem, Message, WsEvent } from '@/api/types'
import { useUserStore } from './user'

export const useChatStore = defineStore('chat', () => {
  const userStore = useUserStore()

  const conversations = ref<ConversationItem[]>([])
  const activeId = ref<number | null>(null)
  /** conversation_id → 消息列表(按 msg_id 升序) */
  const messagesByConversation = ref<Record<number, Message[]>>({})

  const activeConversation = computed(() =>
    conversations.value.find((c) => c.conversation_id === activeId.value) ?? null,
  )
  const activeMessages = computed(() => messagesByConversation.value[activeId.value ?? -1] ?? [])

  // ---------- 数据加载 ----------

  async function loadConversations(): Promise<void> {
    const out = await api.listConversations()
    conversations.value = out.items
  }

  async function loadHistory(conversationId: number): Promise<void> {
    const out = await api.conversationHistory(conversationId)
    const list = [...out.items].reverse()
    messagesByConversation.value[conversationId] = mergeMessages(
      messagesByConversation.value[conversationId] ?? [],
      list,
    )
  }

  async function openConversation(conversationId: number): Promise<void> {
    activeId.value = conversationId
    await loadHistory(conversationId)
    // 打开即已读:上报到最新一条消息
    const msgs = messagesByConversation.value[conversationId] ?? []
    const latest = msgs[msgs.length - 1]
    if (latest && userStore.user) {
      await clearUnread(conversationId)
    }
  }

  async function sendMessage(body: string): Promise<void> {
    if (!activeId.value || !body.trim()) return
    const sent = await api.sendMessage(activeId.value, body.trim())
    upsertMessage(sent)
  }

  async function clearUnread(conversationId: number): Promise<void> {
    const msgs = messagesByConversation.value[conversationId] ?? []
    const latest = msgs[msgs.length - 1]
    if (!latest) return
    // read_index 以用户链 seq 表示;此处直接后端按最新已读处理(骨架简化,见 docs/02-API约定.md)
    await api.markRead(conversationId, latest.msg_id).catch(() => undefined)
    const conv = conversations.value.find((c) => c.conversation_id === conversationId)
    if (conv) conv.unread_count = 0
  }

  // ---------- WS 事件消费 ----------

  async function handleEvent(event: WsEvent): Promise<void> {
    switch (event.type) {
      case 'message.new': {
        const msg = event.data
        upsertMessage(msg)
        const conv = conversations.value.find((c) => c.conversation_id === msg.conversation_id)
        if (conv) {
          conv.last_msg = msg
          conv.update_time = msg.create_time
          if (msg.sender_id !== userStore.user?.user_id) {
            if (conv.conversation_id === activeId.value) await clearUnread(conv.conversation_id)
            else conv.unread_count += 1
          }
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
      case 'read.sync': {
        // 多端已读同步:骨架阶段仅刷新未读数
        const conv = conversations.value.find((c) => c.conversation_id === event.data.conversation_id)
        if (conv) conv.unread_count = 0
        break
      }
      case 'conversation.update': {
        await loadConversations()
        break
      }
      case 'friend.request': {
        // 好友申请实时到达:骨架阶段仅刷新;好友管理页为下一步扩展
        break
      }
    }
  }

  function upsertMessage(msg: Message): void {
    const list = messagesByConversation.value[msg.conversation_id] ?? []
    if (!list.some((m) => m.msg_id === msg.msg_id)) {
      list.push(msg)
      list.sort((a, b) => a.msg_id - b.msg_id)
    }
    messagesByConversation.value[msg.conversation_id] = list
  }

  function mergeMessages(existing: Message[], incoming: Message[]): Message[] {
    const map = new Map(existing.map((m) => [m.msg_id, m]))
    for (const m of incoming) map.set(m.msg_id, m)
    return [...map.values()].sort((a, b) => a.msg_id - b.msg_id)
  }

  // ---------- 连接管理 ----------

  async function startSession(): Promise<void> {
    await loadConversations()
    const initial = await wsClient.initialSync()
    for (const item of initial.items) {
      if (item.kind === 'message' && item.data) {
        upsertMessage(item.data as unknown as Message)
      }
    }
    wsClient.on(handleEvent)
    wsClient.connect()
  }

  function endSession(): void {
    wsClient.disconnect()
    conversations.value = []
    messagesByConversation.value = {}
    activeId.value = null
  }

  return {
    conversations,
    activeId,
    activeConversation,
    activeMessages,
    loadConversations,
    openConversation,
    sendMessage,
    clearUnread,
    handleEvent,
    startSession,
    endSession,
  }
})