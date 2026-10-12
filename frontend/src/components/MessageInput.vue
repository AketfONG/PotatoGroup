<script setup lang="ts">
// 输入区:Enter 发送,Shift+Enter 换行
import { NButton, NInput } from 'naive-ui'
import { useMessage } from 'naive-ui'
import { ref } from 'vue'

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
  } catch {
    message.error('发送失败,请检查网络后重试')
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <div class="input-area">
    <n-input
      v-model:value="draft"
      type="textarea"
      :rows="3"
      placeholder="输入消息,Enter 发送,Shift+Enter 换行"
      :disabled="!chatStore.activeId"
      @keydown.enter.exact.prevent="send"
    />
    <n-button type="primary" :loading="sending" :disabled="!draft.trim()" @click="send">发送</n-button>
  </div>
</template>

<style scoped>
.input-area {
  flex: none;
  display: flex;
  gap: 12px;
  align-items: flex-end;
  padding: 12px 18px 16px;
  background: #fff;
  border-top: 1px solid #eaeef2;
}
</style>