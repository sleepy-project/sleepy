import { createRouter, createWebHistory } from 'vue-router'
import { api } from '@/services/api'
import StatusView from '@/views/StatusView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: StatusView },
    { path: '/setup', component: () => import('@/views/SetupView.vue') },
    { path: '/login', component: () => import('@/views/LoginView.vue') },
    { path: '/admin', component: () => import('@/views/AdminView.vue'), meta: { auth: true } },
    { path: '/tokens', component: () => import('@/views/TokensView.vue'), meta: { auth: true } },
    { path: '/metrics', component: () => import('@/views/MetricsView.vue'), meta: { auth: true } },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ]
})

let initialized: boolean | null = null

router.beforeEach(async (to) => {
  if (initialized === null) {
    try {
      const response = await api.request<{ initialized: boolean }>('/api/v1/init', {}, false)
      initialized = response.initialized
    } catch {
      if (to.path !== '/') return '/'
    }
  }
  if (!initialized && to.path !== '/setup') return '/setup'
  if (initialized && to.path === '/setup') return api.authenticated ? '/admin' : '/login'
  if (to.meta.auth && !api.authenticated) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.path === '/login' && api.authenticated) return '/admin'
})

export default router
