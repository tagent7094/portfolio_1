import { useEffect, useRef, useState } from 'react'
import { Terminal as XTerminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { Plus, X } from 'lucide-react'

interface TermTab {
  id: string
  label: string
  terminal: XTerminal
  fitAddon: FitAddon
  ws: WebSocket | null
}

export default function Terminal() {
  const [tabs, setTabs] = useState<TermTab[]>([])
  const [activeTab, setActiveTab] = useState<string>('')
  const containerRef = useRef<HTMLDivElement>(null)
  const tabsRef = useRef<TermTab[]>([])

  useEffect(() => { tabsRef.current = tabs }, [tabs])

  const createTab = () => {
    const id = `term-${Date.now()}`
    const terminal = new XTerminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: '"JetBrains Mono", "Fira Code", monospace',
      theme: {
        background: '#0c0c10',
        foreground: '#d4d4d8',
        cursor: '#d4d4d8',
        selectionBackground: 'rgba(255,255,255,0.15)',
        black: '#18181b',
        red: '#f87171',
        green: '#4ade80',
        yellow: '#fbbf24',
        blue: '#60a5fa',
        magenta: '#c084fc',
        cyan: '#22d3ee',
        white: '#d4d4d8',
        brightBlack: '#52525b',
        brightRed: '#fca5a5',
        brightGreen: '#86efac',
        brightYellow: '#fde68a',
        brightBlue: '#93c5fd',
        brightMagenta: '#d8b4fe',
        brightCyan: '#67e8f9',
        brightWhite: '#fafafa',
      },
      allowProposedApi: true,
    })
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.loadAddon(new WebLinksAddon())

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/api/os/terminal`)
    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      terminal.onData(data => ws.send(new TextEncoder().encode(data)))
      terminal.onResize(({ cols, rows }) => {
        ws.send(JSON.stringify({ type: 'resize', cols, rows }))
      })
    }
    ws.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer) {
        terminal.write(new Uint8Array(e.data))
      } else {
        terminal.write(e.data)
      }
    }
    ws.onclose = () => terminal.write('\r\n\x1b[31m[Connection closed]\x1b[0m\r\n')

    const tab: TermTab = { id, label: `Shell ${tabsRef.current.length + 1}`, terminal, fitAddon, ws }
    setTabs(prev => [...prev, tab])
    setActiveTab(id)
    return tab
  }

  const closeTab = (id: string) => {
    setTabs(prev => {
      const tab = prev.find(t => t.id === id)
      if (tab) {
        tab.ws?.close()
        tab.terminal.dispose()
      }
      const remaining = prev.filter(t => t.id !== id)
      if (activeTab === id && remaining.length > 0) {
        setActiveTab(remaining[remaining.length - 1].id)
      }
      return remaining
    })
  }

  useEffect(() => {
    createTab()
    return () => {
      tabsRef.current.forEach(t => { t.ws?.close(); t.terminal.dispose() })
    }
  }, [])

  useEffect(() => {
    if (!containerRef.current) return
    const container = containerRef.current
    container.innerHTML = ''
    const tab = tabs.find(t => t.id === activeTab)
    if (!tab) return
    tab.terminal.open(container)
    requestAnimationFrame(() => {
      tab.fitAddon.fit()
      tab.terminal.focus()
    })
  }, [activeTab, tabs])

  useEffect(() => {
    const handle = () => {
      const tab = tabsRef.current.find(t => t.id === activeTab)
      if (tab) tab.fitAddon.fit()
    }
    window.addEventListener('resize', handle)
    const observer = new ResizeObserver(handle)
    if (containerRef.current) observer.observe(containerRef.current)
    return () => { window.removeEventListener('resize', handle); observer.disconnect() }
  }, [activeTab])

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center border-b border-white/[0.06] bg-[#0a0a0e]">
        {tabs.map(t => (
          <div key={t.id} onClick={() => setActiveTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs cursor-pointer border-r border-white/[0.04] ${
              t.id === activeTab ? 'bg-[#0c0c10] text-white/70' : 'text-white/30 hover:text-white/50 hover:bg-white/[0.02]'
            }`}>
            <span>{t.label}</span>
            <button onClick={(e) => { e.stopPropagation(); closeTab(t.id) }} className="p-0.5 rounded hover:bg-white/10"><X size={10} /></button>
          </div>
        ))}
        <button onClick={createTab} className="p-1.5 text-white/30 hover:text-white/50 hover:bg-white/[0.03]"><Plus size={13} /></button>
      </div>
      <div ref={containerRef} className="flex-1 bg-[#0c0c10]" />
    </div>
  )
}
