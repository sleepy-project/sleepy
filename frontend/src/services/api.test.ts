import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClient } from './api'

const tokens = { token: 'old', refresh_token: 'refresh', expires_at: 1 }
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

describe('ApiClient', () => {
  beforeEach(() => localStorage.clear())
  it('starts when browser storage is unavailable', () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementationOnce(() => { throw new DOMException('denied', 'SecurityError') })
    expect(() => new ApiClient()).not.toThrow()
    getItem.mockRestore()

    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => { throw new DOMException('denied', 'SecurityError') })
    const client = new ApiClient()
    expect(() => client.setSession(tokens)).not.toThrow()
    expect(client.tokens).toEqual(tokens)
    setItem.mockRestore()
  })
  it('calls fetch with the global object as its receiver', async () => {
    const fetcher = vi.fn(function (this: typeof globalThis) {
      expect(this).toBe(globalThis)
      return Promise.resolve(json({ ok: true }))
    })
    await new ApiClient(fetcher as typeof fetch).request('/api/test')
  })
  it('injects the access token header', async () => {
    const fetcher = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => { expect(new Headers(init?.headers).get('X-Sleepy-Token')).toBe('old'); return json({ ok: true }) })
    const client = new ApiClient(fetcher as typeof fetch); client.setSession(tokens)
    await client.request('/api/test')
    expect(fetcher).toHaveBeenCalledOnce()
  })
  it('shares one refresh across concurrent requests', async () => {
    let refreshes = 0
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      if (String(url).endsWith('/refresh')) { refreshes++; await new Promise((resolve) => setTimeout(resolve, 5)); return json({ token: 'new', refresh_token: 'refresh', expires_at: 2 }) }
      return new Headers(init?.headers).get('X-Sleepy-Token') === 'new' ? json({ ok: true }) : json({}, 401)
    })
    const client = new ApiClient(fetcher as typeof fetch); client.setSession(tokens)
    await Promise.all([client.request('/a'), client.request('/b')])
    expect(refreshes).toBe(1)
  })
  it('clears the session when refresh fails', async () => {
    const fetcher = vi.fn(async (url: string | URL | Request) => String(url).endsWith('/refresh') ? json({}, 401) : json({}, 401))
    const client = new ApiClient(fetcher as typeof fetch); client.setSession(tokens)
    await expect(client.request('/private')).rejects.toThrow()
    expect(client.tokens).toBeNull(); expect(localStorage.getItem('sleepy.auth')).toBeNull()
  })
})
