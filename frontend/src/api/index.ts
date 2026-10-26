/**
 * 类型化 API 门面:按运行模式分发到真实后端(real.ts)或前端 mock(mockApi.ts)。
 * 契约见 docs/02-API约定.md;组件与 store 不直接拼接 URL、不感知模式。
 */

import { mockApi } from './mock/mockApi'
import * as real from './real'

export type Api = typeof real

/** mock 模式标记:vite --mode mock 时为 true(WS 等据此跳过真实连接) */
export const isMockMode: boolean = import.meta.env.MODE === 'mock'

const impl: Api = isMockMode ? (mockApi satisfies typeof real) : real

// 显式再导出,保持 stores 既有 `import * as api from '@/api'` 用法不变
export const register = impl.register
export const login = impl.login
export const logout = impl.logout
export const myProfile = impl.myProfile
export const updateProfile = impl.updateProfile
export const deleteAccount = impl.deleteAccount
export const getUser = impl.getUser
export const searchUsers = impl.searchUsers
export const listFriends = impl.listFriends
export const deleteFriend = impl.deleteFriend
export const createFriendRequest = impl.createFriendRequest
export const listFriendRequests = impl.listFriendRequests
export const acceptFriendRequest = impl.acceptFriendRequest
export const rejectFriendRequest = impl.rejectFriendRequest
export const listConversations = impl.listConversations
export const createGroup = impl.createGroup
export const createPrivateChat = impl.createPrivateChat
export const conversationDetail = impl.conversationDetail
export const updateConversation = impl.updateConversation
export const addMembers = impl.addMembers
export const removeMember = impl.removeMember
export const leaveConversation = impl.leaveConversation
export const updateMyConversationSettings = impl.updateMyConversationSettings
export const markRead = impl.markRead
export const sendMessage = impl.sendMessage
export const conversationHistory = impl.conversationHistory
export const recallMessage = impl.recallMessage
export const deleteMessage = impl.deleteMessage
export const sync = impl.sync

// ---------- 供类型检查导出 ----------
export type { FriendItem, UserSummary } from './types'
