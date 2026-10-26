<script setup lang="ts">
import { NButton, NInput, useMessage } from 'naive-ui'
import { ref } from 'vue'

import { ApiError } from '@/api/http'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()
const message = useMessage()
const draft = ref('')
const sending = ref(false)

async function send(): Promise<void> {
  const body = draft.value.trim()
  if (!body || sending.value) return
  sending.value = true
  try {
    await chatStore.sendMessage(body)
    draft.value = ''
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '发送失败,请检查网络后重试')
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="input-area">
    <div v-if="chatStore.replyTo" class="reply-bar">
      <span class="reply-text">回复: {{ chatStore.replyTo.body.slice(0, 60) }}</span>
      <a @click="chatStore.setReplyTo(null)">取消</a>
    </div>
    <div class="input-row">
      <n-input
        v-model:value="draft"
        type="textarea"
        :rows="3"
        placeholder="输入消息,Enter 发送,Shift+Enter 换行;右键消息可回复/撤回/删除"
        :disabled="!chatStore.activeId"
        @keydown.enter.exact.prevent="send"
      />
      <n-button type="primary" :loading="sending" :disabled="!draft.trim()" @click="send">发送</n-button>
    </div>
  </div>
</template>

<style scoped>
.input-area {
  flex: none;
  padding: 10px 18px 16px;
  background: var(--surface);
  border-top: 1px solid var(--border);
}

.reply-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
  padding: 6px 12px;
  background: var(--hover);
  border-radius: var(--radius-control);
  border-left: 3px solid var(--accent);
}

.reply-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reply-bar a {
  cursor: pointer;
  color: var(--accent);
  flex: none;
  margin-left: 12px;
}

.input-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}
</style>
