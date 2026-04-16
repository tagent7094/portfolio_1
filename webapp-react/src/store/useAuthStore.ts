import { create } from 'zustand'
import { apiGet, apiPost } from '../api/client'
import { getSubdomainSlug } from '../utils/subdomain'

type AuthStatus = 'unknown' | 'authed' | 'anon'

const ALL_PAGES = ['dashboard', 'generate', 'customize', 'graph', 'coverage', 'workflow', 'history', 'config']

interface AuthState {
  slug: string
  displayName: string
  status: AuthStatus
  error: string | null
  allowedPages: string[]
  bootstrap: () => Promise<void>
  login: (slug: string, password: string) => Promise<boolean>
  logout: () => Promise<void>
  changePassword: (current: string, newPw: string) => Promise<boolean>
}

export const useAuthStore = create<AuthState>((set) => ({
  slug: '',
  displayName: '',
  status: 'unknown',
  error: null,
  allowedPages: ALL_PAGES,

  bootstrap: async () => {
    // Unscoped (dev / apex): treat as authed with all pages
    if (getSubdomainSlug() === null) {
      set({ status: 'authed', slug: 'dev', displayName: 'Local Dev', allowedPages: ALL_PAGES })
      return
    }
    try {
      const me = await apiGet<{ slug: string; display_name: string }>('/api/auth/me')
      // Fetch page permissions
      let pages = ALL_PAGES
      try {
        const perms = await apiGet<{ pages: string[] }>('/api/auth/permissions')
        pages = perms.pages
      } catch {
        // fallback to all pages if permissions endpoint fails
      }
      set({ status: 'authed', slug: me.slug, displayName: me.display_name, allowedPages: pages, error: null })
    } catch {
      set({ status: 'anon', slug: '', displayName: '', allowedPages: [], error: null })
    }
  },

  login: async (slug, password) => {
    set({ error: null })
    try {
      const res = await apiPost<{ ok: boolean; slug: string; display_name: string }>(
        '/api/auth/login',
        { slug, password },
      )
      // Fetch permissions after login
      let pages = ALL_PAGES
      try {
        const perms = await apiGet<{ pages: string[] }>('/api/auth/permissions')
        pages = perms.pages
      } catch {
        // fallback
      }
      set({ status: 'authed', slug: res.slug, displayName: res.display_name, allowedPages: pages, error: null })
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
    set({ status: 'anon', slug: '', displayName: '', allowedPages: [], error: null })
  },

  changePassword: async (current, newPw) => {
    set({ error: null })
    try {
      await apiPost('/api/auth/change-password', { current_password: current, new_password: newPw })
      return true
    } catch (e: any) {
      const msg = String(e?.message || 'Password change failed')
      set({ error: msg.includes('401') ? 'Current password is wrong' : msg })
      return false
    }
  },
}))
