import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/services/api'
import type { AuthTokens } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const initialized = ref<boolean | null>(null)
  const session = ref<AuthTokens | null>(api.tokens)
  const loading = ref(false)
  const authenticated = computed(() => Boolean(session.value?.token))
  api.subscribe((value) => { session.value = value })

  async function checkInitialization() {
    const response = await api.request<{ initialized: boolean }>('/api/v1/init', {}, false)
    initialized.value = response.initialized
    return response.initialized
  }

  async function initialize(password: string) {
    loading.value = true
    try {
      await api.request('/api/v1/init', { method: 'POST', body: JSON.stringify({ password, hashed: false }) }, false)
      initialized.value = true
    } finally { loading.value = false }
  }

  async function login(password: string) {
    loading.value = true
    try {
      const tokens = await api.request<AuthTokens>('/api/v1/auth/login', {
        method: 'POST', body: JSON.stringify({ password, hashed: false, type: 'web', device_uid: getDeviceId() })
      }, false)
      api.setSession(tokens)
    } finally { loading.value = false }
  }

  function logout() { api.setSession(null) }
  return { initialized, session, loading, authenticated, checkInitialization, initialize, login, logout }
})

function getDeviceId() {
  const key = 'sleepy.browser-id'
  try {
    const stored = globalThis.localStorage?.getItem(key)
    if (stored) return stored
  } catch { /* Continue with an in-memory identifier. */ }

  const value = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
  try { globalThis.localStorage?.setItem(key, value) } catch { /* Storage is optional. */ }
  return value
}
