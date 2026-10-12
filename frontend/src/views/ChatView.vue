<script setup lang="ts">
// 聊天主界面:左侧会话列表 + 右侧消息区(骨架阶段的核心布局)
import { NEmpty } from 'naive-ui'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import ConversationList from '@/components/ConversationList.vue'
import MessageInput from '@/components/MessageInput.vue'
import MessageList from '@/components/MessageList.vue'
import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const chatStore = useChatStore()
const router = useRouter()
const started = ref(false)

onMounted(async () => {
  await userStore.restore()
  if (!userStore.loggedIn) {
    await router.replace('/login')
    return
  }
  try {
    await chatStore.startSession()
    started.value = true
  } catch {
    await userStore.logout()
    await router.replace('/login')
  }
})

onBeforeUnmount(() => {
  chatStore.endSession()
})

async function handleLogout(): Promise<void> {
  await userStore.logout()
  await router.replace('/login')
}
</script>

<template>
  <div class="chat-layout">
    <!-- 顶栏 -->
    <header class="chat-header">
      <div class="header-left">
        <span class="logo">🥔 土豆聊天</span>
      </div>
      <div class="header-right">
        <span class="username">{{ userStore.user?.name ?? '' }}</span>
        <a class="logout" @click="handleLogout">退出登录</a>
      </div>
    </header>

    <!-- 主体:会话列表 + 消息区 -->
    <div class="chat-body">
      <aside class="sidebar">
        <ConversationList />
      </aside>
      <main class="chat-main">
        <template v-if="chatStore.activeConversation">
          <div class="chat-main-header">
            <span class="conv-name">{{ chatStore.activeConversation.name ?? '会话' }}</span>
            <span class="conv-meta">
              {{ chatStore.activeConversation.type === 'group'
                ? `${chatStore.activeConversation.member_count} 人`
                : '' }}
            </span>
          </div>
          <MessageList />
          <MessageInput />
        </template>
        <n-empty v-else class="chat-empty" description="选择左侧会话开始聊天" size="large" />
      </main>
    </div>
  </div>
</template>

<style scoped>
.chat-layout {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f3f6f4;
}

.chat-header {
  height: 52px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid #eaeef2;
}

.logo {
  font-weight: 600;
  font-size: 16px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 13px;
  color: #666;
}

.logout {
  color: #d03050;
  cursor: pointer;
}

.chat-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.sidebar {
  width: 280px;
  flex: none;
  background: #fff;
  border-right: 1px solid #eaeef2;
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
}

.chat-main-header {
  height: 48px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
  background: #fff;
  border-bottom: 1px solid #eaeef2;
  font-weight: 500;
}

.conv-meta {
  font-size: 12px;
  color: #999;
  font-weight: 400;
}

.chat-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>