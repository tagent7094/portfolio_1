import { create } from 'zustand'
import { apiGet, apiPost } from '../api/client'
import { getSubdomainSlug } from '../utils/subdomain'

type AuthStatus = 'unknown' | 'authed' | 'anon'

interface AuthState {
  slug: string
  displayName: string
  status: AuthStatus
  error: string | null
  bootstrap: () => Promise<void>
  login: (slug: string, password: string) => Promise<boolean>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  slug: '',
  displayName: '',
  status: 'unknown',
  error: null,

  bootstrap: async () => {
    // Unscoped (dev / apex): treat as authed so existing local flow keeps working
    if (getSubdomainSlug() === null) {
      set({ status: 'authed', slug: 'dev', displayName: 'Local Dev' })
      return
    }
    try {
      const me = await apiGet<{ slug: string; display_name: string }>('/api/auth/me')
      set({ status: 'authed', slug: me.slug, displayName: me.display_name, error: null })
    } catch {
      set({ status: 'anon', slug: '', displayName: '', error: null })
    }
  },

  login: async (slug, password) => {
    set({ error: null })
    try {
      const res = await apiPost<{ ok: boolean; slug: string; display_name: string }>(
        '/api/auth/login',
        { slug, password },
      )
      set({ status: 'authed', slug: res.slug, displayName: res.display_name, error: null })
      return true
    } catch (e: any) {
      const msg = String(e?.message || 'Login failed')
      set({ error: msg.includes('401') ? 'Invalid credentials' : msg })
      return false
    }
  },

  logout: async () => {
    try {
      await apiPost('/api/auth/logout', {})
    } catch {
      // ignore
    }
    set({ status: 'anon', slug: '', displayName: '', error: null })
  },
}))
