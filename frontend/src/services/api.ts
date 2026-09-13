import type { ApiErrorBody, AuthTokens } from '@/types/api'

const STORAGE_KEY = 'sleepy.auth'

type SessionListener = (session: AuthTokens | null) => void

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

export class ApiClient {
  private session: AuthTokens | null = null
  private refreshPromise: Promise<boolean> | null = null
  private listeners = new Set<SessionListener>()

  private fetcher: typeof fetch

  constructor(fetcher: typeof fetch = fetch) {
    this.fetcher = fetcher.bind(globalThis)
    this.restore()
  }

  get tokens() { return this.session }
  get authenticated() { return Boolean(this.session?.token) }

  subscribe(listener: SessionListener) {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  setSession(session: AuthTokens | null) {
    this.session = session
    try {
      if (session) globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(session))
      else globalThis.localStorage?.removeItem(STORAGE_KEY)
    } catch { /* Keep the session in memory when storage is unavailable. */ }
    this.listeners.forEach((listener) => listener(session))
  }

  private restore() {
    try {
      const raw = globalThis.localStorage?.getItem(STORAGE_KEY)
      this.session = raw ? JSON.parse(raw) as AuthTokens : null
    } catch { this.session = null }
  }

  async request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
    const headers = new Headers(init.headers)
    if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    if (this.session?.token) headers.set('X-Sleepy-Token', this.session.token)
    const response = await this.fetcher(path, { ...init, headers })
    if ((response.status === 401 || response.status === 403) && retry && this.session?.refresh_token) {
      if (await this.refresh()) return this.request<T>(path, init, false)
    }
    if (!response.ok) throw await this.toError(response)
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }

  async refresh(): Promise<boolean> {
    if (this.refreshPromise) return this.refreshPromise
    this.refreshPromise = this.performRefresh().finally(() => { this.refreshPromise = null })
    return this.refreshPromise
  }

  private async performRefresh(): Promise<boolean> {
    if (!this.session?.refresh_token) return false
    try {
      const response = await this.fetcher('/api/v1/auth/refresh', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: this.session.token, refresh_token: this.session.refresh_token })
      })
      if (!response.ok) throw await this.toError(response)
      this.setSession(await response.json() as AuthTokens)
      return true
    } catch {
      this.setSession(null)
      return false
    }
  }

  private async toError(response: Response) {
    let body: ApiErrorBody = {}
    try { body = await response.json() as ApiErrorBody } catch { /* empty response */ }
    return new ApiError(response.status, body.detail || body.message || `请求失败 (${response.status})`)
  }
}

export const api = new ApiClient()
