import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/services/api'
import type { DeviceToken, Metrics, StatusPreset, StatusSnapshot } from '@/types/api'

export const useDashboardStore = defineStore('dashboard', () => {
  const snapshot = ref<StatusSnapshot | null>(null)
  const presets = ref<StatusPreset[]>([])
  const tokens = ref<DeviceToken[]>([])
  const metrics = ref<Metrics | null>(null)
  const loading = ref(false)
  const error = ref('')

  async function loadPublic() {
    loading.value = true; error.value = ''
    try {
      const [status, configured] = await Promise.all([
        api.request<StatusSnapshot>('/api/v1/status', {}, false),
        api.request<StatusPreset[]>('/api/v1/status/presets', {}, false)
      ])
      snapshot.value = status; presets.value = configured
    } catch (reason) { error.value = reason instanceof Error ? reason.message : '加载失败' }
    finally { loading.value = false }
  }

  async function loadAdmin() {
    await loadPublic()
    const [tokenList, metricData] = await Promise.all([
      api.request<DeviceToken[]>('/api/v1/tokens'), api.request<Metrics>('/api/v1/metrics')
    ])
    tokens.value = tokenList; metrics.value = metricData
  }

  async function setStatus(status: number) {
    await api.request('/api/v1/status', { method: 'PUT', body: JSON.stringify({ status }) }); await loadPublic()
  }
  async function setPrivacy(value: boolean) {
    await api.request('/api/v1/privacy', { method: 'PUT', body: JSON.stringify({ private: value }) }); await loadPublic()
  }
  async function removeDevice(id: string) {
    await api.request(`/api/v1/devices/${encodeURIComponent(id)}`, { method: 'DELETE' }); await loadPublic()
  }
  async function clearDevices() {
    await api.request('/api/v1/devices', { method: 'DELETE' }); await loadPublic()
  }
  async function createToken(name: string) {
    const created = await api.request<{ token: string }>('/api/v1/tokens', { method: 'POST', body: JSON.stringify({ name }) })
    tokens.value = await api.request<DeviceToken[]>('/api/v1/tokens')
    return created.token
  }
  async function revokeToken(token: string) {
    await api.request(`/api/v1/tokens/${encodeURIComponent(token)}`, { method: 'DELETE' })
    tokens.value = await api.request<DeviceToken[]>('/api/v1/tokens')
  }
  async function loadMetrics() { metrics.value = await api.request<Metrics>('/api/v1/metrics') }

  return { snapshot, presets, tokens, metrics, loading, error, loadPublic, loadAdmin, setStatus, setPrivacy, removeDevice, clearDevices, createToken, revokeToken, loadMetrics }
})
