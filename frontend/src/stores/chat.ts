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
    // read_index 必须是「我的用户链 seq」,由历史接口随每条消息返回(history 的 seq 字段)。
    // 不能用 latest.msg_id:那是全局消息 ID,与服务端 seq 不是一回事,上报会被判越界拒绝
    // (见 docs/02 第 6 节「已读上报的两条约束」)。
    const readIndex = latest.seq
    if (readIndex === undefined) return
    await api.markRead(conversationId, readIndex)
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
      case 'message.delete': {
        // 本端多设备同步删除:我在别的设备删了这条,这里也要移除(仅本地,不影响其他成员)
        const { msg_id, conversation_id } = event.data
        removeMessage(conversation_id, msg_id)
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

  /** 本地移除一条消息(本地删除,或收到 message.delete 多端同步事件) */
  function removeMessage(conversationId: number, msgId: number): void {
    const list = messagesByConversation.value[conversationId]
    if (!list) return
    messagesByConversation.value[conversationId] = list.filter((m) => m.msg_id !== msgId)
  }

  /** 本地删除一条消息:先落服务端(仅对我生效),再更新本地列表 */
  async function deleteMessage(conversationId: number, msgId: number): Promise<void> {
    await api.deleteMessage(conversationId, msgId)
    removeMessage(conversationId, msgId)
  }

  // ---------- 连接管理 ----------

  async function startSession(): Promise<void> {
    await loadConversations()
    const initial = await wsClient.initialSync()
    for (const item of initial.items) {
      if (item.kind === 'message' && item.data) {
        upsertMessage(item.data as unknown as Message)
      } else if (item.kind === 'delete' && item.data) {
        // 登录补拉时也要应用「我删过的」标记,否则刷新后已删消息会重新出现
        const payload = item.data as { msg_id?: number; conversation_id?: number }
        if (payload.msg_id !== undefined && payload.conversation_id !== undefined) {
          removeMessage(payload.conversation_id, payload.msg_id)
        }
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
    deleteMessage,
    handleEvent,
    startSession,
    endSession,
  }
})