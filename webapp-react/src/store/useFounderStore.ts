import { create } from 'zustand'
import type { Founder } from '../types/api'
import { apiGet, apiPost } from '../api/client'
import { getSubdomainSlug } from '../utils/subdomain'

interface FounderState {
  founders: Founder[]
  active: string
  loading: boolean
  load: () => Promise<void>
  switchFounder: (slug: string) => Promise<void>
}

export const useFounderStore = create<FounderState>((set) => ({
  founders: [],
  active: 'sharath',
  loading: false,

  load: async () => {
    // Subdomain mode: skip the founders API; pin to the slug from the URL
    const subdomain = getSubdomainSlug()
    if (subdomain) {
      set({
        founders: [{
          slug: subdomain,
          display_name: subdomain.charAt(0).toUpperCase() + subdomain.slice(1),
          active: true,
          has_graph: true,
        }],
        active: subdomain,
        loading: false,
      })
      return
    }

    set({ loading: true })
    try {
      const data = await apiGet<{ founders: Founder[]; active: string }>('/api/founders')
      set({ founders: data.founders, active: data.active })
    } catch (e) {
      console.error('Failed to load founders:', e)
    } finally {
      set({ loading: false })
    }
  },

  switchFounder: async (slug: string) => {
    // No-op in subdomain mode — founders cannot switch
    if (getSubdomainSlug()) return
    await apiPost('/api/founders/active', { slug })
    set({ active: slug })
  },
}))
