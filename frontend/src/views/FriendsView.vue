<script setup lang="ts">
import { MessageCircle, Search, UserPlus } from '@lucide/vue'
import {
  NButton,
  NEmpty,
  NInput,
  NSpace,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from 'naive-ui'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import { ApiError } from '@/api/http'
import { useChatStore } from '@/stores/chat'
import { useFriendsStore } from '@/stores/friends'
import { useUserStore } from '@/stores/user'

const friendsStore = useFriendsStore()
const chatStore = useChatStore()
const userStore = useUserStore()
const router = useRouter()
const message = useMessage()

const keyword = ref('')
const searching = ref(false)

onMounted(() => {
  void friendsStore.refresh().catch((e) => {
    message.error(e instanceof ApiError ? e.message : '加载好友失败')
  })
})

async function doSearch(): Promise<void> {
  searching.value = true
  try {
    await friendsStore.search(keyword.value)
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '搜索失败')
  } finally {
    searching.value = false
  }
}

async function addFriend(userId: number): Promise<void> {
  try {
    await friendsStore.sendRequest(userId)
    message.success('好友申请已发送')
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '发送失败')
  }
}

async function accept(id: number): Promise<void> {
  try {
    await friendsStore.accept(id)
    message.success('已同意')
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '操作失败')
  }
}

async function reject(id: number): Promise<void> {
  try {
    await friendsStore.reject(id)
    message.success('已拒绝')
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '操作失败')
  }
}

async function remove(userId: number, name: string): Promise<void> {
  try {
    await friendsStore.remove(userId)
    message.success(`已删除好友 ${name}`)
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '删除失败')
  }
}

async function openChat(userId: number): Promise<void> {
  try {
    await chatStore.startPrivateChat(userId)
    await router.push('/')
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '无法打开私聊')
  }
}

function isSelf(userId: number): boolean {
  return userId === userStore.user?.user_id
}

function isFriend(userId: number): boolean {
  return friendsStore.friends.some((f) => f.user_id === userId)
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="friends-page page-centred page-scroll">
    <n-tabs type="line" animated>
      <n-tab-pane name="list" tab="好友列表">
        <n-empty
          v-if="friendsStore.friends.length === 0"
          description="还没有好友,去「添加」搜索用户吧"
          class="empty"
        />
        <div v-for="f in friendsStore.friends" :key="f.user_id" class="row">
          <div class="avatar">{{ (f.remark || f.name).slice(0, 1) }}</div>
          <div class="info">
            <div class="name">
              {{ f.remark || f.name }}
              <n-tag v-if="f.group_name" size="small" :bordered="false">{{ f.group_name }}</n-tag>
              <n-tag v-if="f.online" size="small" type="success" :bordered="false">在线</n-tag>
            </div>
            <div class="sub">{{ f.remark ? f.name : '' }}</div>
          </div>
          <n-space>
            <n-button size="small" type="primary" @click="openChat(f.user_id)">
              <template #icon>
                <AppIcon :icon="MessageCircle" :size="14" />
              </template>
              发消息
            </n-button>
            <n-button size="small" quaternary type="error" @click="remove(f.user_id, f.name)">删除</n-button>
          </n-space>
        </div>
      </n-tab-pane>

      <n-tab-pane name="requests" :tab="`申请(${friendsStore.pendingIncoming.length})`">
        <n-empty
          v-if="friendsStore.requests.length === 0"
          description="暂无好友申请"
          class="empty"
        />
        <div v-for="r in friendsStore.requests" :key="r.request_id" class="row">
          <div class="info grow">
            <div class="name">
              {{ r.from_user?.name ?? `用户 ${r.to_user_id}` }}
              <n-tag size="small" :type="r.status === 'pending' ? 'warning' : 'default'" :bordered="false">
                {{ r.status === 'pending' ? '待处理' : r.status === 'accepted' ? '已同意' : '已拒绝' }}
              </n-tag>
            </div>
            <div class="sub">{{ formatTime(r.create_time) }}</div>
          </div>
          <n-space v-if="r.status === 'pending' && r.from_user">
            <n-button size="small" type="primary" @click="accept(r.request_id)">同意</n-button>
            <n-button size="small" @click="reject(r.request_id)">拒绝</n-button>
          </n-space>
        </div>
      </n-tab-pane>

      <n-tab-pane name="add" tab="添加">
        <n-space class="search-bar">
          <n-input
            v-model:value="keyword"
            placeholder="按用户名搜索"
            clearable
            @keyup.enter="doSearch"
          >
            <template #prefix>
              <AppIcon :icon="Search" :size="16" />
            </template>
          </n-input>
          <n-button type="primary" :loading="searching" @click="doSearch">
            <template #icon>
              <AppIcon :icon="Search" :size="16" />
            </template>
            搜索
          </n-button>
        </n-space>
        <n-empty
          v-if="friendsStore.searchResults.length === 0"
          description="输入关键词搜索用户"
          class="empty"
        />
        <div v-for="u in friendsStore.searchResults" :key="u.user_id" class="row">
          <div class="avatar">{{ u.name.slice(0, 1) }}</div>
          <div class="info grow">
            <div class="name">{{ u.name }}</div>
          </div>
          <n-button
            v-if="!isSelf(u.user_id) && !isFriend(u.user_id)"
            size="small"
            type="primary"
            @click="addFriend(u.user_id)"
          >
            <template #icon>
              <AppIcon :icon="UserPlus" :size="14" />
            </template>
            加好友
          </n-button>
          <n-tag v-else-if="isFriend(u.user_id)" size="small" :bordered="false">已是好友</n-tag>
          <n-tag v-else size="small" :bordered="false">我</n-tag>
        </div>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<style scoped>
.friends-page {
  background: var(--bg);
}

.search-bar {
  margin-bottom: 16px;
  width: 100%;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 8px;
  border-bottom: 1px solid var(--border);
}

.avatar {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-control);
  background: var(--avatar-bg);
  color: var(--avatar-fg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  flex: none;
}

.info {
  min-width: 0;
}

.info.grow {
  flex: 1;
}

.name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  color: var(--text);
}

.sub {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.empty {
  margin-top: 48px;
}
</style>
