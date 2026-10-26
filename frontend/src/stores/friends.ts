/** 好友列表与申请 store。 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import * as api from '@/api'
import type { FriendItem, FriendRequest, UserSummary } from '@/api/types'

export const useFriendsStore = defineStore('friends', () => {
  const friends = ref<FriendItem[]>([])
  const requests = ref<FriendRequest[]>([])
  const searchResults = ref<UserSummary[]>([])
  const loading = ref(false)

  const pendingIncoming = computed(() =>
    requests.value.filter((r) => r.status === 'pending'),
  )

  async function loadFriends(): Promise<void> {
    const out = await api.listFriends()
    friends.value = out.items
  }

  async function loadRequests(): Promise<void> {
    const out = await api.listFriendRequests()
    requests.value = out.items
  }

  async function refresh(): Promise<void> {
    loading.value = true
    try {
      await Promise.all([loadFriends(), loadRequests()])
    } finally {
      loading.value = false
    }
  }

  async function search(keyword: string): Promise<void> {
    if (!keyword.trim()) {
      searchResults.value = []
      return
    }
    const out = await api.searchUsers(keyword.trim())
    searchResults.value = out.items
  }

  async function sendRequest(targetUserId: number): Promise<void> {
    await api.createFriendRequest(targetUserId)
    await loadRequests()
  }

  async function accept(requestId: number): Promise<void> {
    await api.acceptFriendRequest(requestId)
    await refresh()
  }

  async function reject(requestId: number): Promise<void> {
    await api.rejectFriendRequest(requestId)
    await loadRequests()
  }

  async function remove(friendUserId: number): Promise<void> {
    await api.deleteFriend(friendUserId)
    friends.value = friends.value.filter((f) => f.user_id !== friendUserId)
  }

  return {
    friends,
    requests,
    searchResults,
    loading,
    pendingIncoming,
    loadFriends,
    loadRequests,
    refresh,
    search,
    sendRequest,
    accept,
    reject,
    remove,
  }
})
