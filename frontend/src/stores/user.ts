/** 认证与用户信息 store。 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as api from '@/api'
import { setToken } from '@/api/http'
import type { UserProfile, UserSummary } from '@/api/types'

export const useUserStore = defineStore('user', () => {
  const user = ref<UserSummary | null>(null)
  const profile = ref<UserProfile | null>(null)
  const loggedIn = ref(false)

  async function login(name: string, password: string): Promise<void> {
    const out = await api.login(name, password)
    setToken(out.token)
    user.value = out.user
    loggedIn.value = true
  }

  async function register(name: string, password: string): Promise<void> {
    await api.register(name, password)
    await login(name, password)
  }

  async function logout(): Promise<void> {
    try {
      await api.logout()
    } finally {
      setToken(null)
      user.value = null
      profile.value = null
      loggedIn.value = false
    }
  }

  async function restore(): Promise<void> {
    if (!user.value) {
      try {
        const p = await api.myProfile()
        profile.value = p
        user.value = { user_id: p.user_id, name: p.name, avatar: p.avatar, online: true }
        loggedIn.value = true
      } catch {
        loggedIn.value = false
      }
    }
  }

  async function loadProfile(): Promise<UserProfile> {
    const p = await api.myProfile()
    profile.value = p
    user.value = { user_id: p.user_id, name: p.name, avatar: p.avatar, online: true }
    return p
  }

  async function updateProfile(payload: {
    name?: string
    avatar?: string | null
    email?: string | null
    phone?: string | null
    old_password?: string
    new_password?: string
  }): Promise<UserProfile> {
    const p = await api.updateProfile(payload)
    profile.value = p
    user.value = { user_id: p.user_id, name: p.name, avatar: p.avatar, online: true }
    return p
  }

  async function deleteAccount(): Promise<void> {
    await api.deleteAccount()
    setToken(null)
    user.value = null
    profile.value = null
    loggedIn.value = false
  }

  return {
    user,
    profile,
    loggedIn,
    login,
    register,
    logout,
    restore,
    loadProfile,
    updateProfile,
    deleteAccount,
  }
})
