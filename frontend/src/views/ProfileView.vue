<script setup lang="ts">
import { LogOut, ShieldAlert } from '@lucide/vue'
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NSpace,
  useDialog,
  useMessage,
} from 'naive-ui'
import type { FormInst, FormRules } from 'naive-ui'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import { ApiError } from '@/api/http'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const saving = ref(false)
const formRef = ref<FormInst | null>(null)
const pwdRef = ref<FormInst | null>(null)

const form = reactive({
  name: '',
  email: '',
  phone: '',
  avatar: '',
})

const pwd = reactive({
  old_password: '',
  new_password: '',
  confirm: '',
})

const profileRules: FormRules = {
  name: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 32, message: '用户名长度需在 2-32 个字符之间', trigger: 'blur' },
  ],
}

const pwdRules: FormRules = {
  old_password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, max: 64, message: '密码长度需在 8-64 位之间', trigger: 'blur' },
    {
      validator: (_r, value: string) => {
        if (!value) return true
        if (!/[A-Za-z]/.test(value) || !/[0-9]/.test(value)) {
          return new Error('密码需同时包含字母和数字')
        }
        return true
      },
      trigger: 'blur',
    },
  ],
  confirm: [
    {
      required: true,
      validator: () => {
        if (pwd.confirm !== pwd.new_password) return new Error('两次输入的新密码不一致')
        return true
      },
      trigger: 'blur',
    },
  ],
}

onMounted(async () => {
  loading.value = true
  try {
    const p = await userStore.loadProfile()
    form.name = p.name
    form.email = p.email ?? ''
    form.phone = p.phone ?? ''
    form.avatar = p.avatar ?? ''
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '加载资料失败')
  } finally {
    loading.value = false
  }
})

async function saveProfile(): Promise<void> {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    await userStore.updateProfile({
      name: form.name,
      email: form.email || null,
      phone: form.phone || null,
      avatar: form.avatar || null,
    })
    message.success('资料已保存')
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function changePassword(): Promise<void> {
  try {
    await pwdRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    await userStore.updateProfile({
      old_password: pwd.old_password,
      new_password: pwd.new_password,
    })
    message.success('密码已修改')
    pwd.old_password = ''
    pwd.new_password = ''
    pwd.confirm = ''
  } catch (e) {
    message.error(e instanceof ApiError ? e.message : '修改密码失败')
  } finally {
    saving.value = false
  }
}

async function handleLogout(): Promise<void> {
  await userStore.logout()
  await router.replace('/login')
}

function confirmDelete(): void {
  dialog.warning({
    title: '注销账号',
    content: '注销后账号及相关数据将按服务端约定清理,且无法恢复。确认继续?',
    positiveText: '确认注销',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await userStore.deleteAccount()
        message.success('账号已注销')
        await router.replace('/login')
      } catch (e) {
        message.error(e instanceof ApiError ? e.message : '注销失败')
      }
    },
  })
}
</script>

<template>
  <div class="profile-page page-centred page-scroll">
    <n-card title="个人资料" :bordered="false" class="panel">
      <n-form ref="formRef" :model="form" :rules="profileRules" label-placement="left" label-width="80">
        <n-form-item label="用户名" path="name">
          <n-input v-model:value="form.name" />
        </n-form-item>
        <n-form-item label="邮箱" path="email">
          <n-input v-model:value="form.email" placeholder="选填" />
        </n-form-item>
        <n-form-item label="手机" path="phone">
          <n-input v-model:value="form.phone" placeholder="选填" />
        </n-form-item>
        <n-form-item label="头像 URL" path="avatar">
          <n-input v-model:value="form.avatar" placeholder="选填,填写图片地址" />
        </n-form-item>
        <n-button type="primary" :loading="saving" @click="saveProfile">保存资料</n-button>
      </n-form>
    </n-card>

    <n-card title="修改密码" :bordered="false" class="panel">
      <n-form ref="pwdRef" :model="pwd" :rules="pwdRules" label-placement="left" label-width="80">
        <n-form-item label="当前密码" path="old_password">
          <n-input v-model:value="pwd.old_password" type="password" show-password-on="click" />
        </n-form-item>
        <n-form-item label="新密码" path="new_password">
          <n-input v-model:value="pwd.new_password" type="password" show-password-on="click" />
        </n-form-item>
        <n-form-item label="确认密码" path="confirm">
          <n-input v-model:value="pwd.confirm" type="password" show-password-on="click" />
        </n-form-item>
        <n-button type="primary" :loading="saving" @click="changePassword">更新密码</n-button>
      </n-form>
    </n-card>

    <n-card title="账号操作" :bordered="false" class="panel">
      <n-space>
        <n-button @click="handleLogout">
          <template #icon>
            <AppIcon :icon="LogOut" :size="16" />
          </template>
          退出登录
        </n-button>
        <n-button type="error" secondary @click="confirmDelete">
          <template #icon>
            <AppIcon :icon="ShieldAlert" :size="16" />
          </template>
          注销账号
        </n-button>
      </n-space>
    </n-card>
  </div>
</template>

<style scoped>
.profile-page {
  background: var(--bg);
}

.panel {
  margin-bottom: 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-surface);
}
</style>
