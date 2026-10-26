<script setup lang="ts">
import { Moon, Sun } from '@lucide/vue'
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  useMessage,
} from 'naive-ui'
import type { FormInst, FormRules } from 'naive-ui'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppIcon from '@/components/AppIcon.vue'
import { ApiError } from '@/api/http'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const themeStore = useThemeStore()
const router = useRouter()
const route = useRoute()
const message = useMessage()

const mode = ref<'login' | 'register'>('login')
const formRef = ref<FormInst | null>(null)
const name = ref('')
const password = ref('')
const loading = ref(false)

const rules: FormRules = {
  name: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 32, message: '用户名长度需在 2-32 个字符之间', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
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
}

async function submit(): Promise<void> {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    if (mode.value === 'login') {
      await userStore.login(name.value, password.value)
      message.success('登录成功')
    } else {
      await userStore.register(name.value, password.value)
      message.success('注册成功,已自动登录')
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : '网络异常,请稍后重试'
    message.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="theme-toggle">
      <n-button
        quaternary
        circle
        size="small"
        :aria-label="themeStore.mode === 'light' ? '切换深色模式' : '切换浅色模式'"
        @click="themeStore.toggle()"
      >
        <AppIcon :icon="themeStore.mode === 'light' ? Moon : Sun" :size="16" />
      </n-button>
    </div>
    <n-card class="login-card" :bordered="false">
      <div class="brand">
        <h1 class="brand-title">土豆聊天</h1>
        <p class="brand-sub">即时通讯</p>
      </div>

      <n-form ref="formRef" :model="{ name, password }" :rules="rules" label-placement="top" size="large">
        <n-form-item label="用户名" path="name">
          <n-input v-model:value="name" placeholder="2-32 个字符,支持中文" :input-props="{ autocomplete: 'username' }" />
        </n-form-item>
        <n-form-item label="密码" path="password">
          <n-input
            v-model:value="password"
            type="password"
            show-password-on="click"
            placeholder="至少 8 位,需包含字母和数字"
            :input-props="{ autocomplete: 'current-password' }"
            @keyup.enter="submit"
          />
        </n-form-item>
        <n-button type="primary" block size="large" :loading="loading" @click="submit">
          {{ mode === 'login' ? '登录' : '注册' }}
        </n-button>
      </n-form>

      <div class="switch-mode">
        {{ mode === 'login' ? '还没有账号?' : '已有账号?' }}
        <a href="#" @click.prevent="mode = mode === 'login' ? 'register' : 'login'">
          {{ mode === 'login' ? '注册一个' : '去登录' }}
        </a>
      </div>
    </n-card>
  </div>
</template>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  position: relative;
}

.theme-toggle {
  position: absolute;
  top: 16px;
  right: 16px;
}

.login-card {
  width: 380px;
  border-radius: var(--radius-surface);
  background: var(--surface);
  border: 1px solid var(--border);
}

.brand {
  text-align: center;
  margin-bottom: 24px;
}

.brand-title {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 650;
  color: var(--text);
  letter-spacing: 0.02em;
}

.brand-sub {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}

.switch-mode {
  margin-top: 16px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}

.switch-mode a {
  color: var(--accent);
  cursor: pointer;
  margin-left: 4px;
}
</style>
