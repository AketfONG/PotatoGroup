<script setup lang="ts">
// 会话列表:未读角标、置顶标识、最近消息预览(骨架阶段;好友/群管理为下一步扩展)
import { NBadge, NEmpty, NScrollbar } from 'naive-ui'

import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'

const chatStore = useChatStore()
const userStore = useUserStore()

function formatTime(ts: number): string {
  const d = new Date(ts * 1000)
  const today = new Date()
  const sameDay = d.toDateString() === today.toDateString()
  return sameDay
    ? d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

function preview(body: string, senderId: number | null): string {
  if (senderId !== null && senderId === userStore.user?.user_id) return `我: ${body}`
  return body
}
</script>

<template>
  <div class="conv-list">
    <div class="conv-list-title">会话</div>
    <n-scrollbar>
      <n-empty
        v-if="chatStore.conversations.length === 0"
        class="conv-empty"
        description="还没有会话,等待下一步好友功能上线"
        size="small"
      />
      <div
        v-for="conv in chatStore.conversations"
        :key="conv.conversation_id"
        class="conv-item"
        :class="{ active: conv.conversation_id === chatStore.activeId }"
        @click="chatStore.openConversation(conv.conversation_id)"
      >
        <n-badge :value="conv.unread_count" :max="99" :show="conv.unread_count > 0">
          <div class="conv-avatar">{{ (conv.name ?? '?').slice(0, 1) }}</div>
        </n-badge>
        <div class="conv-info">
          <div class="conv-row">
            <span class="conv-name">
              {{ conv.pinned ? '📌 ' : '' }}{{ conv.name ?? '会话' }}
            </span>
            <span class="conv-time">
              {{ conv.last_msg ? formatTime(conv.last_msg.create_time) : '' }}
            </span>
          </div>
          <div class="conv-preview">
            {{ conv.last_msg ? preview(conv.last_msg.body, conv.last_msg.sender_id) : '暂无消息' }}
          </div>
        </div>
        <span v-if="conv.muted" class="muted-icon" title="免打扰">🔇</span>
      </div>
    </n-scrollbar>
  </div>
</template>

<style scoped>
.conv-list {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.conv-list-title {
  padding: 14px 16px 8px;
  font-size: 13px;
  color: #999;
}

.conv-empty {
  margin-top: 60px;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.conv-item:hover {
  background: #f5f7fa;
}

.conv-item.active {
  background: #e8f3ea;
}

.conv-avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: #d4e5c9;
  color: #4a6b3a;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 600;
}

.conv-info {
  flex: 1;
  min-width: 0;
}

.conv-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.conv-name {
  font-size: 14px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-time {
  font-size: 11px;
  color: #aaa;
  flex: none;
}

.conv-preview {
  font-size: 12px;
  color: #999;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 3px;
}

.muted-icon {
  font-size: 12px;
  flex: none;
}
</style>