export interface AuthTokens { token: string; refresh_token: string; expires_at: number | null; type?: string }
export interface StatusPreset { id: number; name: string; desc: string; color: string }
export interface Device { id: string; name: string; status: string; using: boolean; fields: Record<string, unknown>; last_updated: number }
export interface StatusSnapshot { time: number; status: number; last_updated: number; devices: Device[]; private: boolean }
export interface DeviceToken { token: string; name: string | null; created: number; last_active: number; expire: number }
export interface Metrics { success: boolean; enabled: boolean; time?: number; time_local?: string; timezone?: string; daily?: Record<string, number>; weekly?: Record<string, number>; monthly?: Record<string, number>; yearly?: Record<string, number>; total?: Record<string, number> }
export interface ApiErrorBody { detail?: string; message?: string }
