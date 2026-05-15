import { create } from 'zustand'

export type WindowType = 'file-manager' | 'terminal' | 'system-monitor' | 'process-manager' | 'log-viewer' | 'llm-logs'

export interface OsWindow {
  id: string
  type: WindowType
  title: string
  minimized: boolean
  maximized: boolean
  x: number
  y: number
  w: number
  h: number
  zIndex: number
}

const DEFAULT_SIZE: Record<WindowType, { w: number; h: number }> = {
  'file-manager': { w: 800, h: 520 },
  'terminal': { w: 720, h: 440 },
  'system-monitor': { w: 640, h: 480 },
  'process-manager': { w: 780, h: 500 },
  'log-viewer': { w: 800, h: 500 },
  'llm-logs': { w: 820, h: 500 },
}

const TITLES: Record<WindowType, string> = {
  'file-manager': 'File Manager',
  'terminal': 'Terminal',
  'system-monitor': 'System Monitor',
  'process-manager': 'Processes',
  'log-viewer': 'Log Viewer',
  'llm-logs': 'LLM Logs',
}

let _nextZ = 10
let _offset = 0

interface OsState {
  windows: OsWindow[]
  activeWindowId: string | null
  openWindow: (type: WindowType) => void
  closeWindow: (id: string) => void
  minimizeWindow: (id: string) => void
  maximizeWindow: (id: string) => void
  focusWindow: (id: string) => void
  moveWindow: (id: string, x: number, y: number) => void
  resizeWindow: (id: string, w: number, h: number) => void
}

export const useOsStore = create<OsState>((set) => ({
  windows: [],
  activeWindowId: null,

  openWindow: (type) => set((s) => {
    const existing = s.windows.find(w => w.type === type && !w.minimized)
    if (existing) {
      _nextZ++
      return {
        windows: s.windows.map(w => w.id === existing.id ? { ...w, zIndex: _nextZ, minimized: false } : w),
        activeWindowId: existing.id,
      }
    }
    const minimized = s.windows.find(w => w.type === type && w.minimized)
    if (minimized) {
      _nextZ++
      return {
        windows: s.windows.map(w => w.id === minimized.id ? { ...w, minimized: false, zIndex: _nextZ } : w),
        activeWindowId: minimized.id,
      }
    }
    _nextZ++
    _offset = (_offset + 30) % 150
    const size = DEFAULT_SIZE[type]
    const win: OsWindow = {
      id: `${type}-${Date.now()}`,
      type,
      title: TITLES[type],
      minimized: false,
      maximized: false,
      x: 80 + _offset,
      y: 40 + _offset,
      w: size.w,
      h: size.h,
      zIndex: _nextZ,
    }
    return { windows: [...s.windows, win], activeWindowId: win.id }
  }),

  closeWindow: (id) => set((s) => ({
    windows: s.windows.filter(w => w.id !== id),
    activeWindowId: s.activeWindowId === id ? null : s.activeWindowId,
  })),

  minimizeWindow: (id) => set((s) => ({
    windows: s.windows.map(w => w.id === id ? { ...w, minimized: true } : w),
    activeWindowId: s.activeWindowId === id ? null : s.activeWindowId,
  })),

  maximizeWindow: (id) => set((s) => ({
    windows: s.windows.map(w => w.id === id ? { ...w, maximized: !w.maximized } : w),
  })),

  focusWindow: (id) => set((s) => {
    _nextZ++
    return {
      windows: s.windows.map(w => w.id === id ? { ...w, zIndex: _nextZ } : w),
      activeWindowId: id,
    }
  }),

  moveWindow: (id, x, y) => set((s) => ({
    windows: s.windows.map(w => w.id === id ? { ...w, x, y } : w),
  })),

  resizeWindow: (id, width, height) => set((s) => ({
    windows: s.windows.map(win => win.id === id ? { ...win, w: width, h: height } : win),
  })),
}))
