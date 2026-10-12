<script setup lang="ts">
// 消息区:自己/对方左右分列气泡,纯文本渲染(防 XSS,见 docs/02-API约定.md 第 8 节)
import { NScrollbar } from 'naive-ui'
import { nextTick, ref, watch } from 'vue'

import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'

const chatStore = useChatStore()
const userStore = useUserStore()
const scrollbarRef = ref()

watch(
  () => chatStore.activeMessages.length,
  () => {
    // 新消息时滚动到底部
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
</script>

<template>
  <div class="message-area">
    <n-scrollbar ref="scrollbarRef">
      <div class="message-list">
        <div
          v-for="msg in chatStore.activeMessages"
          :key="msg.msg_id"
          class="message-row"
          :class="{ mine: isMine(msg.sender_id) }"
        >
          <div class="bubble">
            <div class="bubble-body">{{ msg.body }}</div>
            <div class="bubble-time">{{ formatTime(msg.create_time) }}</div>
          </div>
        </div>
      </div>
    </n-scrollbar>
  </div>
</template>

<style scoped>
.message-area {
  flex: 1;
  min-height: 0;
  padding: 16px 18px;
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

.bubble {
  max-width: 62%;
  padding: 8px 12px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.mine .bubble {
  background: #95ec69;
}

.bubble-body {
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
}

.bubble-time {
  font-size: 10px;
  color: #999;
  text-align: right;
  margin-top: 4px;
}
</style>