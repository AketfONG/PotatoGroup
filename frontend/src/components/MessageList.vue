<script setup lang="ts">
import { NButton, NDropdown, NScrollbar, useMessage } from 'naive-ui'
import type { DropdownOption } from 'naive-ui'
import { nextTick, ref, watch } from 'vue'

import { ApiError } from '@/api/http'
import type { Message } from '@/api/types'
import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'

const chatStore = useChatStore()
const userStore = useUserStore()
const message = useMessage()
const scrollbarRef = ref()
const highlightId = ref<number | null>(null)
const menuMsgId = ref<number | null>(null)

watch(
  () => chatStore.activeMessages.length,
  () => {
    void nextTick(() => {
      scrollbarRef.value?.scrollTo({ top: 999999, behavior: 'smooth' })
    })
  },
)

function isMine(senderId: number | null): boolean {
  return senderId === userStore.user?.user_id
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function canRecall(msg: Message): boolean {
  if (!isMine(msg.sender_id)) return false
  if (msg.body === '[消息已撤回]') return false
  const age = Date.now() / 1000 - msg.create_time
  return age <= 120
}

function menuOptions(msg: Message): DropdownOption[] {
  const opts: DropdownOption[] = [{ label: '回复', key: 'reply' }]
  if (canRecall(msg)) opts.push({ label: '撤回', key: 'recall' })
  opts.push({ label: '删除(仅自己)', key: 'delete' })
  if (msg.reply_to) opts.push({ label: '定位原消息', key: 'locate' })
  return opts
}

async function onMenu(key: string | number, msg: Message): Promise<void> {
  try {
    if (key === 'reply') {
      chatStore.setReplyTo(msg)
    } else if (key === 'recall') {
      await chatStore.recallMessage(msg)
      message.success('已撤回')
    } else if (key === 'delete') {
      await chatStore.deleteMessage(msg.conversation_id, msg.msg_id)
      message.success('已删除')
    } else if (key === 'locate' && msg.reply_to) {
      const result = await chatStore.locateMessage(msg.reply_to)
      if (result === 'ok') {
        highlightId.value = msg.reply_to
        await nextTick()
        const el = document.getElementById(`msg-${msg.reply_to}`)
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        window.setTimeout(() => {
          highlightId.value = null
        }, 2000)
      } else {
        message.warning('原消息不可见或已删除')
      }
    }
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '操作失败')
  }
}

async function loadOlder(): Promise<void> {
  try {
    await chatStore.loadOlderHistory()
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '加载历史失败')
  }
}

function replyPreview(msg: Message): string {
  if (!msg.reply_to) return ''
  const target = chatStore.findMessage(msg.conversation_id, msg.reply_to)
  if (!target) return `回复 #${msg.reply_to}`
  const text = target.body.slice(0, 40)
  return `回复: ${text}`
}
</script>

<template>
  <div class="message-area">
    <div v-if="chatStore.hasMoreHistory" class="load-older">
      <n-button text size="small" :loading="chatStore.loadingOlder" @click="loadOlder">
        加载更早消息
      </n-button>
    </div>
    <n-scrollbar ref="scrollbarRef">
      <div class="message-list">
        <div
          v-for="msg in chatStore.activeMessages"
          :id="`msg-${msg.msg_id}`"
          :key="msg.msg_id"
          class="message-row"
          :class="{ mine: isMine(msg.sender_id), highlight: highlightId === msg.msg_id }"
        >
          <n-dropdown
            trigger="manual"
            placement="bottom-start"
            :show="menuMsgId === msg.msg_id"
            :options="menuOptions(msg)"
            @clickoutside="menuMsgId = null"
            @select="(k) => { menuMsgId = null; void onMenu(k, msg) }"
          >
            <div class="bubble" @contextmenu.prevent="menuMsgId = msg.msg_id">
              <div v-if="msg.reply_to" class="reply-ref">{{ replyPreview(msg) }}</div>
              <div class="bubble-body">{{ msg.body }}</div>
              <div class="bubble-time">{{ formatTime(msg.create_time) }}</div>
            </div>
          </n-dropdown>
        </div>
      </div>
    </n-scrollbar>
  </div>
</template>

<style scoped>
.message-area {
  flex: 1;
  min-height: 0;
  padding: 8px 18px 16px;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}

.load-older {
  text-align: center;
  padding: 4px 0 8px;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message-row {
  display: flex;
}

.message-row.mine {
  justify-content: flex-end;
}

.message-row.highlight .bubble {
  outline: 2px solid var(--accent);
}

.bubble {
  max-width: 62%;
  padding: 8px 12px;
  border-radius: var(--radius-bubble);
  background: var(--bubble-other);
  border: 1px solid var(--border);
  cursor: pointer;
}

.mine .bubble {
  background: var(--bubble-mine);
  border-color: transparent;
}

.reply-ref {
  font-size: 12px;
  color: var(--text-muted);
  border-left: 2px solid var(--accent);
  padding-left: 8px;
  margin-bottom: 6px;
}

.bubble-body {
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
  color: var(--text);
}

.bubble-time {
  font-size: 10px;
  color: var(--text-muted);
  text-align: right;
  margin-top: 4px;
}
</style>
