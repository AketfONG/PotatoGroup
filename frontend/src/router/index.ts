import { createRouter, createWebHistory } from 'vue-router'

import { getToken } from '@/api/http'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: '登录 - 土豆聊天' },
    },
    {
      path: '/',
      component: () => import('@/components/MainLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'chat',
          component: () => import('@/views/ChatView.vue'),
          meta: { title: '土豆聊天', requiresAuth: true },
        },
        {
          path: 'friends',
          name: 'friends',
          component: () => import('@/views/FriendsView.vue'),
          meta: { title: '好友 - 土豆聊天', requiresAuth: true },
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('@/views/ProfileView.vue'),
          meta: { title: '资料 - 土豆聊天', requiresAuth: true },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  document.title = String(to.meta.title ?? '土豆聊天')
  if (to.meta.requiresAuth && !getToken()) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
