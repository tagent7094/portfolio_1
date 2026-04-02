import { create } from 'zustand'
import type { Founder } from '../types/api'
import { apiGet, apiPost } from '../api/client'

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
    await apiPost('/api/founders/active', { slug })
    set({ active: slug })
  },
}))
