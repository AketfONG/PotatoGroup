<script setup lang="ts">
import { NButton, NCheckbox, NCheckboxGroup, NForm, NFormItem, NInput, NModal, useMessage } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { ApiError } from '@/api/http'
import { useChatStore } from '@/stores/chat'
import { useFriendsStore } from '@/stores/friends'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [boolean]; created: [] }>()

const friendsStore = useFriendsStore()
const chatStore = useChatStore()
const message = useMessage()

const name = ref('')
const memberIds = ref<number[]>([])
const loading = ref(false)

const friendOptions = computed(() =>
  friendsStore.friends.map((f) => ({
    label: f.remark || f.name,
    value: f.user_id,
  })),
)

watch(
  () => props.show,
  (v) => {
    if (v) {
      name.value = ''
      memberIds.value = []
      void friendsStore.loadFriends()
    }
  },
)

async function submit(): Promise<void> {
  if (!name.value.trim()) {
    message.warning('请输入群名称')
    return
  }
  if (memberIds.value.length === 0) {
    message.warning('请至少选择一位好友')
    return
  }
  loading.value = true
  try {
    await chatStore.createGroup(name.value.trim(), memberIds.value)
    message.success('群聊已创建')
    emit('update:show', false)
    emit('created')
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '创建失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    title="创建群聊"
    style="width: 420px"
    @update:show="emit('update:show', $event)"
  >
    <n-form label-placement="top">
      <n-form-item label="群名称">
        <n-input v-model:value="name" placeholder="给群起个名字" maxlength="32" />
      </n-form-item>
      <n-form-item label="选择好友">
        <n-checkbox-group v-model:value="memberIds">
          <div class="member-list">
            <n-checkbox
              v-for="opt in friendOptions"
              :key="opt.value"
              :value="opt.value"
              :label="opt.label"
            />
          </div>
        </n-checkbox-group>
      </n-form-item>
    </n-form>
    <template #footer>
      <n-button @click="emit('update:show', false)">取消</n-button>
      <n-button type="primary" :loading="loading" style="margin-left: 8px" @click="submit">创建</n-button>
    </template>
  </n-modal>
</template>

<style scoped>
.member-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 240px;
  overflow: auto;
}
</style>
