<script setup lang="ts">
import { BellOff, Ellipsis, Pin, UsersRound } from '@lucide/vue'
import { NBadge, NButton, NDropdown, NEmpty, NScrollbar, useMessage } from 'naive-ui'
import type { DropdownOption } from 'naive-ui'
import { h, ref } from 'vue'

import { ApiError } from '@/api/http'
import AppIcon from '@/components/AppIcon.vue'
import CreateGroupModal from '@/components/CreateGroupModal.vue'
import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'

const chatStore = useChatStore()
const userStore = useUserStore()
const message = useMessage()
const showCreateGroup = ref(false)

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

function menuOptions(conv: { pinned: boolean; muted: boolean }): DropdownOption[] {
  return [
    {
      label: conv.pinned ? '取消置顶' : '置顶',
      key: 'pin',
      icon: () => h(AppIcon, { icon: Pin, size: 14 }),
    },
    {
      label: conv.muted ? '关闭免打扰' : '开启免打扰',
      key: 'mute',
      icon: () => h(AppIcon, { icon: BellOff, size: 14 }),
    },
  ]
}

async function onMenu(key: string | number, conversationId: number, pinned: boolean, muted: boolean): Promise<void> {
  try {
    if (key === 'pin') await chatStore.setPinned(conversationId, !pinned)
    if (key === 'mute') await chatStore.setMuted(conversationId, !muted)
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '设置失败')
  }
}
</script>

<template>
  <div class="conv-list">
    <div class="conv-list-head">
      <span class="conv-list-title">会话</span>
      <n-button size="tiny" quaternary @click="showCreateGroup = true">
        <template #icon>
          <AppIcon :icon="UsersRound" :size="14" />
        </template>
        建群
      </n-button>
    </div>
    <n-scrollbar>
      <n-empty
        v-if="chatStore.sortedConversations.length === 0"
        class="conv-empty"
        description="还没有会话,去好友页发起私聊或建群"
        size="small"
      />
      <div
        v-for="conv in chatStore.sortedConversations"
        :key="conv.conversation_id"
        class="conv-item"
        :class="{ active: conv.conversation_id === chatStore.activeId }"
        tabindex="0"
        role="button"
        @click="chatStore.openConversation(conv.conversation_id)"
        @keydown.enter="chatStore.openConversation(conv.conversation_id)"
      >
        <n-badge :value="conv.unread_count" :max="99" :show="conv.unread_count > 0">
          <div class="conv-avatar">{{ (conv.name ?? '?').slice(0, 1) }}</div>
        </n-badge>
        <div class="conv-info">
          <div class="conv-row">
            <span class="conv-name">
              <AppIcon v-if="conv.pinned" :icon="Pin" :size="12" class="pin-mark" />
              {{ conv.name ?? '会话' }}
            </span>
            <span class="conv-time">
              {{ conv.last_msg ? formatTime(conv.last_msg.create_time) : '' }}
            </span>
          </div>
          <div class="conv-preview">
            {{ conv.last_msg ? preview(conv.last_msg.body, conv.last_msg.sender_id) : '暂无消息' }}
          </div>
        </div>
        <n-dropdown
          trigger="click"
          :options="menuOptions(conv)"
          @select="(k) => onMenu(k, conv.conversation_id, conv.pinned, conv.muted)"
        >
          <button type="button" class="more" aria-label="会话操作" @click.stop>
            <AppIcon :icon="Ellipsis" :size="16" />
          </button>
        </n-dropdown>
        <AppIcon v-if="conv.muted" :icon="BellOff" :size="14" class="muted-icon" title="免打扰" />
      </div>
    </n-scrollbar>
    <CreateGroupModal v-model:show="showCreateGroup" />
  </div>
</template>

<style scoped>
.conv-list {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--surface);
}

.conv-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 12px 8px 16px;
}

.conv-list-title {
  font-size: 13px;
  color: var(--text-muted);
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
  transition: background 0.15s ease;
  border-radius: 0;
}

.conv-item:hover {
  background: var(--hover);
}

.conv-item.active {
  background: var(--active);
}

.conv-avatar {
  width: 42px;
  height: 42px;
  border-radius: var(--radius-control);
  background: var(--avatar-bg);
  color: var(--avatar-fg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
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
  color: var(--text);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.pin-mark {
  color: var(--accent);
  flex: none;
}

.conv-time {
  font-size: 11px;
  color: var(--text-muted);
  flex: none;
}

.conv-preview {
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 3px;
}

.more {
  font-size: 14px;
  color: var(--text-muted);
  padding: 4px;
  flex: none;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: var(--radius-control);
  display: inline-flex;
  align-items: center;
}

.more:hover {
  background: var(--hover);
  color: var(--text);
}

.muted-icon {
  color: var(--text-muted);
  flex: none;
}
</style>
