<script setup lang="ts">
import {
  NButton,
  NCheckbox,
  NCheckboxGroup,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NInput,
  NSpace,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { ApiError } from '@/api/http'
import { useChatStore } from '@/stores/chat'
import { useFriendsStore } from '@/stores/friends'
import { useUserStore } from '@/stores/user'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [boolean] }>()

const chatStore = useChatStore()
const friendsStore = useFriendsStore()
const userStore = useUserStore()
const message = useMessage()
const dialog = useDialog()

const nameEdit = ref('')
const announcementEdit = ref('')
const inviteIds = ref<number[]>([])
const showInvite = ref(false)

const detail = computed(() => chatStore.groupDetail)
const myRole = computed(() => {
  const me = detail.value?.members.find((m) => m.user.user_id === userStore.user?.user_id)
  return me?.role ?? 'member'
})
const canManage = computed(() => myRole.value === 'owner' || myRole.value === 'admin')

const inviteCandidates = computed(() => {
  const memberIds = new Set(detail.value?.members.map((m) => m.user.user_id) ?? [])
  return friendsStore.friends.filter((f) => !memberIds.has(f.user_id))
})

watch(
  () => props.show,
  async (v) => {
    if (v && chatStore.activeId) {
      try {
        await chatStore.refreshGroupDetail()
        nameEdit.value = detail.value?.name ?? ''
        announcementEdit.value = detail.value?.announcement ?? ''
        await friendsStore.loadFriends()
      } catch (e) {
        message.error(e instanceof ApiError ? e.message : '加载群信息失败')
      }
    }
  },
)

async function saveInfo(): Promise<void> {
  try {
    await chatStore.updateGroupInfo({
      name: nameEdit.value.trim() || undefined,
      announcement: announcementEdit.value,
    })
    message.success('群信息已更新')
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '更新失败')
  }
}

async function doInvite(): Promise<void> {
  if (inviteIds.value.length === 0) {
    message.warning('请选择要邀请的好友')
    return
  }
  try {
    await chatStore.inviteMembers(inviteIds.value)
    message.success('已邀请')
    inviteIds.value = []
    showInvite.value = false
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '邀请失败')
  }
}

function kick(userId: number, name: string): void {
  dialog.warning({
    title: '移除成员',
    content: `确认将 ${name} 移出本群?`,
    positiveText: '移除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await chatStore.kickMember(userId)
        message.success('已移除')
      } catch (e) {
        message.error(e instanceof ApiError ? e.message : '移除失败')
      }
    },
  })
}

function leave(): void {
  dialog.warning({
    title: '退出群聊',
    content: '退出后将无法接收本群消息,确认退出?',
    positiveText: '退出',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await chatStore.leaveGroup()
        message.success('已退出群聊')
        emit('update:show', false)
      } catch (e) {
        message.error(e instanceof ApiError ? e.message : '退出失败')
      }
    },
  })
}

function roleLabel(role: string): string {
  if (role === 'owner') return '群主'
  if (role === 'admin') return '管理员'
  return '成员'
}
</script>

<template>
  <n-drawer :show="show" :width="360" @update:show="emit('update:show', $event)">
    <n-drawer-content title="群管理" closable>
      <template v-if="detail">
        <section class="section">
          <h4>群名称</h4>
          <n-input v-model:value="nameEdit" :disabled="!canManage" maxlength="32" />
          <h4>群公告</h4>
          <n-input
            v-model:value="announcementEdit"
            type="textarea"
            :rows="3"
            :disabled="!canManage"
            placeholder="暂无公告"
          />
          <n-button
            v-if="canManage"
            type="primary"
            size="small"
            style="margin-top: 8px"
            @click="saveInfo"
          >
            保存
          </n-button>
        </section>

        <section class="section">
          <div class="section-head">
            <h4>成员 ({{ detail.members.length }})</h4>
            <n-button v-if="canManage" size="tiny" @click="showInvite = !showInvite">邀请</n-button>
          </div>
          <div v-if="showInvite" class="invite-box">
            <n-empty v-if="inviteCandidates.length === 0" description="没有可邀请的好友" size="small" />
            <n-checkbox-group v-else v-model:value="inviteIds">
              <div v-for="f in inviteCandidates" :key="f.user_id" class="invite-row">
                <n-checkbox :value="f.user_id" :label="f.remark || f.name" />
              </div>
            </n-checkbox-group>
            <n-button size="small" type="primary" style="margin-top: 8px" @click="doInvite">确认邀请</n-button>
          </div>
          <div v-for="m in detail.members" :key="m.user.user_id" class="member-row">
            <div>
              <span class="m-name">{{ m.user.name }}</span>
              <n-tag size="tiny" :bordered="false" style="margin-left: 6px">{{ roleLabel(m.role) }}</n-tag>
            </div>
            <n-button
              v-if="canManage && m.role === 'member' && m.user.user_id !== userStore.user?.user_id"
              size="tiny"
              quaternary
              type="error"
              @click="kick(m.user.user_id, m.user.name)"
            >
              移除
            </n-button>
          </div>
        </section>

        <n-space vertical style="margin-top: 24px">
          <n-button block type="error" secondary @click="leave">退出群聊</n-button>
          <p class="hint">群主转让等能力待后端契约扩展后接入。</p>
        </n-space>
      </template>
      <n-empty v-else description="加载中或非群聊" />
    </n-drawer-content>
  </n-drawer>
</template>

<style scoped>
.section {
  margin-bottom: 20px;
}

.section h4 {
  margin: 12px 0 8px;
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 500;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.member-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}

.m-name {
  color: var(--text);
  font-size: 14px;
}

.invite-box {
  padding: 8px;
  background: var(--hover);
  border-radius: var(--radius-surface);
  margin-bottom: 8px;
}

.invite-row {
  margin: 4px 0;
}

.hint {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
}
</style>
