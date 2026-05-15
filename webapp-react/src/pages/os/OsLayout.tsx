import { useEffect, useRef, useState } from 'react'
import {
  FolderOpen, TerminalSquare, Activity, Cpu, ScrollText, Brain,
  Minus, X, Maximize2,
} from 'lucide-react'
import { useOsStore, type WindowType, type OsWindow } from '../../store/useOsStore'
import { apiGet } from '../../api/client'
import SystemMonitor from './SystemMonitor'
import FileManager from './FileManager'
import ProcessManager from './ProcessManager'
import LogViewer from './LogViewer'
import LlmLogs from './LlmLogs'
import Terminal from './Terminal'

const APPS: { type: WindowType; icon: typeof FolderOpen; label: string; color: string }[] = [
  { type: 'file-manager', icon: FolderOpen, label: 'Files', color: '#60a5fa' },
  { type: 'terminal', icon: TerminalSquare, label: 'Terminal', color: '#4ade80' },
  { type: 'system-monitor', icon: Activity, label: 'Monitor', color: '#f87171' },
  { type: 'process-manager', icon: Cpu, label: 'Processes', color: '#fbbf24' },
  { type: 'log-viewer', icon: ScrollText, label: 'Logs', color: '#c084fc' },
  { type: 'llm-logs', icon: Brain, label: 'LLM Logs', color: '#fb923c' },
]

function WindowContent({ type }: { type: WindowType }) {
  switch (type) {
    case 'system-monitor': return <SystemMonitor />
    case 'file-manager': return <FileManager />
    case 'process-manager': return <ProcessManager />
    case 'log-viewer': return <LogViewer />
    case 'llm-logs': return <LlmLogs />
    case 'terminal': return <Terminal />
  }
}

function WindowFrame({ win }: { win: OsWindow }) {
  const { closeWindow, minimizeWindow, maximizeWindow, focusWindow, moveWindow, resizeWindow } = useOsStore()
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null)
  const resizeRef = useRef<{ startX: number; startY: number; origW: number; origH: number } | null>(null)

  const onDragStart = (e: React.MouseEvent) => {
    if (win.maximized) return
    e.preventDefault()
    focusWindow(win.id)
    dragRef.current = { startX: e.clientX, startY: e.clientY, origX: win.x, origY: win.y }
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      moveWindow(win.id, dragRef.current.origX + ev.clientX - dragRef.current.startX, dragRef.current.origY + ev.clientY - dragRef.current.startY)
    }
    const onUp = () => { dragRef.current = null; window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const onResizeStart = (e: React.MouseEvent) => {
    if (win.maximized) return
    e.preventDefault(); e.stopPropagation()
    focusWindow(win.id)
    resizeRef.current = { startX: e.clientX, startY: e.clientY, origW: win.w, origH: win.h }
    const onMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return
      resizeWindow(win.id, Math.max(320, resizeRef.current.origW + ev.clientX - resizeRef.current.startX), Math.max(200, resizeRef.current.origH + ev.clientY - resizeRef.current.startY))
    }
    const onUp = () => { resizeRef.current = null; window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  if (win.minimized) return null

  const appMeta = APPS.find(a => a.type === win.type)

  const style: React.CSSProperties = win.maximized
    ? { position: 'absolute', top: 0, left: 0, right: 0, bottom: 48, zIndex: win.zIndex }
    : { position: 'absolute', top: win.y, left: win.x, width: win.w, height: win.h, zIndex: win.zIndex }

  return (
    <div style={style} className="flex flex-col rounded-lg overflow-hidden shadow-2xl border border-white/[0.08] bg-[#111116]" onMouseDown={() => focusWindow(win.id)}>
      {/* Title bar */}
      <div onMouseDown={onDragStart} onDoubleClick={() => maximizeWindow(win.id)}
        className="flex items-center gap-2 h-9 px-3 bg-[#18181f] border-b border-white/[0.06] select-none cursor-grab active:cursor-grabbing shrink-0">
        {appMeta && <appMeta.icon size={13} style={{ color: appMeta.color }} />}
        <span className="text-xs text-white/60 flex-1 truncate">{win.title}</span>
        <button onClick={() => minimizeWindow(win.id)} className="p-1 rounded hover:bg-white/10 text-white/30 hover:text-white/50"><Minus size={12} /></button>
        <button onClick={() => maximizeWindow(win.id)} className="p-1 rounded hover:bg-white/10 text-white/30 hover:text-white/50"><Maximize2 size={12} /></button>
        <button onClick={() => closeWindow(win.id)} className="p-1 rounded hover:bg-red-500/20 text-white/30 hover:text-red-400"><X size={12} /></button>
      </div>
      {/* Content */}
      <div className="flex-1 overflow-hidden">
        <WindowContent type={win.type} />
      </div>
      {/* Resize handle */}
      {!win.maximized && (
        <div onMouseDown={onResizeStart} className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize" />
      )}
    </div>
  )
}

export default function OsLayout() {
  const { windows, openWindow, focusWindow } = useOsStore()
  const [time, setTime] = useState(new Date())
  const [cpuMini, setCpuMini] = useState(0)
  const [memMini, setMemMini] = useState(0)

  useEffect(() => {
    const iv = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(iv)
  }, [])

  useEffect(() => {
    const poll = async () => {
      try {
        const s = await apiGet<{ cpu_percent: number; memory: { percent: number } }>('/api/os/stats')
        setCpuMini(s.cpu_percent)
        setMemMini(s.memory.percent)
      } catch {}
    }
    poll()
    const iv = setInterval(poll, 10000)
    return () => clearInterval(iv)
  }, [])

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col" style={{ background: 'linear-gradient(135deg, #050507 0%, #0a0f1a 50%, #0d0a15 100%)' }}>
      {/* Desktop area */}
      <div className="flex-1 relative overflow-hidden">
        {/* Desktop grid of icons */}
        {windows.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="grid grid-cols-3 gap-6">
              {APPS.map(app => (
                <button key={app.type} onClick={() => openWindow(app.type)}
                  className="flex flex-col items-center gap-2 p-4 rounded-xl hover:bg-white/5 transition-colors group">
                  <div className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ background: `${app.color}15`, border: `1px solid ${app.color}25` }}>
                    <app.icon size={24} style={{ color: app.color }} />
                  </div>
                  <span className="text-xs text-white/50 group-hover:text-white/70">{app.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Windows */}
        {windows.map(win => <WindowFrame key={win.id} win={win} />)}
      </div>

      {/* Taskbar */}
      <div className="h-12 bg-[#0c0c10]/90 backdrop-blur-xl border-t border-white/[0.06] flex items-center px-2 gap-1 shrink-0">
        {/* Dock icons */}
        {APPS.map(app => {
          const isOpen = windows.some(w => w.type === app.type)
          return (
            <button key={app.type} onClick={() => openWindow(app.type)}
              className={`relative flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition-colors ${
                isOpen ? 'bg-white/[0.08] text-white/70' : 'text-white/35 hover:bg-white/[0.04] hover:text-white/55'
              }`}>
              <app.icon size={14} style={{ color: isOpen ? app.color : undefined }} />
              <span className="hidden sm:inline">{app.label}</span>
              {isOpen && <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full" style={{ background: app.color }} />}
            </button>
          )
        })}

        {/* Open windows in taskbar */}
        <div className="flex-1 flex items-center gap-1 ml-2 overflow-x-auto">
          {windows.filter(w => w.minimized).map(w => {
            const meta = APPS.find(a => a.type === w.type)
            return (
              <button key={w.id} onClick={() => { focusWindow(w.id); useOsStore.getState().minimizeWindow(w.id) }}
                className="flex items-center gap-1.5 px-2 py-1 rounded bg-white/5 text-xs text-white/40 hover:text-white/60 hover:bg-white/[0.08]">
                {meta && <meta.icon size={11} style={{ color: meta.color }} />}
                <span className="truncate max-w-[100px]">{w.title}</span>
              </button>
            )
          })}
        </div>

        {/* System tray */}
        <div className="flex items-center gap-3 pr-2 text-xs text-white/30">
          <div className="flex items-center gap-1.5">
            <Cpu size={11} />
            <span className="font-mono" style={{ color: cpuMini > 80 ? '#f87171' : cpuMini > 50 ? '#fbbf24' : 'rgba(255,255,255,0.35)' }}>{cpuMini}%</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Activity size={11} />
            <span className="font-mono" style={{ color: memMini > 80 ? '#f87171' : memMini > 50 ? '#fbbf24' : 'rgba(255,255,255,0.35)' }}>{memMini}%</span>
          </div>
          <div className="w-px h-4 bg-white/[0.06]" />
          <span className="font-mono">
            {time.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
      </div>
    </div>
  )
}
