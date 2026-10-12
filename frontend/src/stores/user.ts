/** 认证与用户信息 store。 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as api from '@/api'
import { setToken } from '@/api/http'
import type { UserSummary } from '@/api/types'

export const useUserStore = defineStore('user', () => {
  const user = ref<UserSummary | null>(null)
  const loggedIn = ref(false)

  async function login(name: string, password: string): Promise<void> {
    const out = await api.login(name, password)
    setToken(out.token)
    user.value = out.user
    loggedIn.value = true
  }

  async function register(name: string, password: string): Promise<void> {
    await api.register(name, password)
    // 注册后自动登录,减少一步跳转
    await login(name, password)
  }

  async function logout(): Promise<void> {
    try {
      await api.logout()
    } finally {
      setToken(null)
      user.value = null
      loggedIn.value = false
    }
  }

  /** 页面刷新后恢复登录态 */
  async function restore(): Promise<void> {
    if (!user.value) {
      try {
        const profile = await api.myProfile()
        user.value = { user_id: profile.user_id, name: profile.name, avatar: profile.avatar, online: true }
        loggedIn.value = true
      } catch {
        loggedIn.value = false
      }
    }
  }

  return { user, loggedIn, login, register, logout, restore }
})