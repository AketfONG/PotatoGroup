<script setup lang="ts">
import { ArrowLeft } from '@lucide/vue'
import { NButton, NEmpty, NSpace } from 'naive-ui'
import { computed, ref } from 'vue'

import AppIcon from '@/components/AppIcon.vue'
import ConversationList from '@/components/ConversationList.vue'
import GroupManageDrawer from '@/components/GroupManageDrawer.vue'
import MessageInput from '@/components/MessageInput.vue'
import MessageList from '@/components/MessageList.vue'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()
const showGroup = ref(false)

/** 窄屏:有活动会话时只显示聊天区 */
const paneOpen = computed(() => chatStore.activeId !== null)

function backToList(): void {
  chatStore.clearActiveConversation()
}
</script>

<template>
  <div class="chat-body" :class="{ 'pane-open': paneOpen }">
    <aside class="sidebar">
      <ConversationList />
    </aside>
    <main class="chat-main">
      <template v-if="chatStore.activeConversation">
        <div class="chat-main-header">
          <div class="title-block">
            <n-button
              class="back-btn"
              quaternary
              circle
              size="small"
              aria-label="返回会话列表"
              @click="backToList"
            >
              <AppIcon :icon="ArrowLeft" :size="18" />
            </n-button>
            <span class="conv-name">{{ chatStore.activeConversation.name ?? '会话' }}</span>
            <span class="conv-meta">
              {{
                chatStore.activeConversation.type === 'group'
                  ? `${chatStore.activeConversation.member_count} 人`
                  : '私聊'
              }}
            </span>
          </div>
          <n-space>
            <n-button
              v-if="chatStore.activeConversation.type === 'group'"
              size="small"
              quaternary
              @click="showGroup = true"
            >
              群管理
            </n-button>
          </n-space>
        </div>
        <MessageList />
        <MessageInput />
        <GroupManageDrawer v-model:show="showGroup" />
      </template>
      <n-empty v-else class="chat-empty" description="选择左侧会话开始聊天" size="large" />
    </main>
  </div>
</template>

<style scoped>
.chat-body {
  flex: 1;
  display: flex;
  min-height: 0;
  height: 100%;
}

.sidebar {
  width: 280px;
  flex: none;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: var(--bg);
}

.chat-main-header {
  height: 48px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.title-block {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.back-btn {
  display: none;
  flex: none;
}

.conv-name {
  font-weight: 500;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-meta {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 400;
  flex: none;
}

.chat-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 720px) {
  .sidebar {
    width: 100%;
    border-right: none;
  }

  .chat-main {
    display: none;
  }

  .chat-body.pane-open .sidebar {
    display: none;
  }

  .chat-body.pane-open .chat-main {
    display: flex;
    width: 100%;
  }

  .back-btn {
    display: inline-flex;
  }

  .chat-main-header {
    padding: 0 10px;
  }
}
</style>
