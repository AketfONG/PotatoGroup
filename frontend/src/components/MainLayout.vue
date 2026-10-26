<script setup lang="ts">
/**
 * 已登录壳层:玻璃拟态顶栏 + 导航 + 主题切换 + 用户胶囊(资料/退出)。
 * 页面切换带轻微淡入上移动画(transform/opacity,GPU 友好)。
 */
import { ChevronDown, LogOut, MessageSquare, Moon, Sun, User, Users } from '@lucide/vue'
import { NButton, NDropdown, type DropdownOption } from 'naive-ui'
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import { useChatStore } from '@/stores/chat'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const chatStore = useChatStore()
const themeStore = useThemeStore()
const router = useRouter()
const route = useRoute()
const ready = ref(false)

onMounted(async () => {
  await userStore.restore()
  if (!userStore.loggedIn) {
    await router.replace('/login')
    return
  }
  try {
    await chatStore.startSession()
    ready.value = true
  } catch {
    await userStore.logout()
    await router.replace('/login')
  }
})

onBeforeUnmount(() => {
  chatStore.endSession()
})

function navClass(path: string): string {
  return route.path === path ? 'nav-link active' : 'nav-link'
}

async function go(path: string): Promise<void> {
  await router.push(path)
}

const userName = computed(() => userStore.user?.name ?? '')
const userInitial = computed(() => userName.value.charAt(0).toUpperCase() || '?')
const userAvatar = computed(() => userStore.user?.avatar ?? null)

function renderIcon(icon: typeof User) {
  return () => h(AppIcon, { icon, size: 16 })
}

const userMenuOptions: DropdownOption[] = [
  { label: '个人资料', key: 'profile', icon: renderIcon(User) },
  { type: 'divider', key: 'd1' },
  { label: '退出登录', key: 'logout', icon: renderIcon(LogOut), props: { class: 'danger-item' } },
]

async function onUserMenuSelect(key: string | number): Promise<void> {
  if (key === 'profile') {
    await router.push('/profile')
  } else if (key === 'logout') {
    await userStore.logout()
    await router.replace('/login')
  }
}
</script>

<template>
  <div class="shell">
    <header class="shell-header">
      <div class="header-left">
        <span class="logo">土豆聊天</span>
        <nav class="nav" aria-label="主导航">
          <a :class="navClass('/')" href="/" @click.prevent="go('/')">
            <AppIcon :icon="MessageSquare" :size="16" />
            <span>会话</span>
          </a>
          <a :class="navClass('/friends')" href="/friends" @click.prevent="go('/friends')">
            <AppIcon :icon="Users" :size="16" />
            <span>好友</span>
          </a>
        </nav>
      </div>
      <div class="header-right">
        <n-button
          quaternary
          circle
          size="small"
          :aria-label="themeStore.mode === 'light' ? '切换深色模式' : '切换浅色模式'"
          @click="themeStore.toggle()"
        >
          <AppIcon :icon="themeStore.mode === 'light' ? Moon : Sun" :size="16" />
        </n-button>
        <n-dropdown
          trigger="click"
          :options="userMenuOptions"
          :show-arrow="false"
          @select="onUserMenuSelect"
        >
          <button
            type="button"
            class="user-chip"
            :aria-label="`用户菜单:${userName}`"
            aria-haspopup="menu"
          >
            <img v-if="userAvatar" :src="userAvatar" alt="" class="avatar-img" />
            <span v-else class="avatar-dot" aria-hidden="true">{{ userInitial }}</span>
            <span class="user-chip-name">{{ userName }}</span>
            <AppIcon :icon="ChevronDown" :size="14" class="chev" />
          </button>
        </n-dropdown>
      </div>
    </header>
    <div v-if="ready" class="shell-body">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" :key="route.path" />
        </transition>
      </router-view>
    </div>
  </div>
</template>

<style scoped>
.shell {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: transparent; /* 页面底渐变由 body 承载,玻璃层透出 */
  color: var(--text);
}

.shell-header {
  position: sticky;
  top: 0;
  z-index: 20;
  min-height: 52px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 20px;
  /* 渐进模糊玻璃层 */
  background: var(--surface-glass);
  -webkit-backdrop-filter: blur(14px) saturate(160%);
  backdrop-filter: blur(14px) saturate(160%);
  border-bottom: 1px solid color-mix(in srgb, var(--border) 65%, transparent);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 24px;
  min-width: 0;
  flex: 1;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
}

.logo {
  font-weight: 650;
  font-size: 16px;
  color: var(--text);
  letter-spacing: 0.01em;
  flex: none;
}

.nav {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  min-width: 0;
}

.nav-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--text-muted);
  cursor: pointer;
  text-decoration: none;
  padding: 6px 12px;
  border-radius: var(--radius-control);
  white-space: nowrap;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.nav-link:hover {
  background: var(--hover);
  color: var(--text);
}

.nav-link.active {
  color: var(--accent);
  background: var(--accent-soft);
}

/* ---------- 用户胶囊 ---------- */

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px 4px 6px;
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  background: var(--accent-soft);
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  max-width: 220px;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.user-chip:hover {
  background: var(--accent-soft-hover);
}

.user-chip:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.avatar-dot,
.avatar-img {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  flex: none;
}

.avatar-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  background: var(--avatar-bg);
  color: var(--avatar-fg);
}

.user-chip-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chev {
  color: var(--text-muted);
}

.shell-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto; /* 页面在玻璃顶栏下方滚动 */
  overflow-x: hidden;
}

/* ---------- 页面切换动画(仅 transform/opacity) ---------- */

.page-enter-active,
.page-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (max-width: 720px) {
  .shell-header {
    padding: 8px 12px;
    flex-wrap: wrap;
  }

  .header-left {
    width: 100%;
    gap: 10px;
  }

  .user-chip {
    max-width: 160px;
  }

  .user-chip-name {
    max-width: 80px;
  }
}
</style>
