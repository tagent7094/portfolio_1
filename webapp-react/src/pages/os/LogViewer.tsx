import { useEffect, useRef, useState } from 'react'
import { Search, Pause, Play, ArrowDown, X } from 'lucide-react'

const LOG_SOURCES = [
  { id: 'tagent', label: 'Tagent' },
  { id: 'nginx-access', label: 'Nginx Access' },
  { id: 'nginx-error', label: 'Nginx Error' },
  { id: 'syslog', label: 'Syslog' },
]

function severityColor(line: string) {
  const upper = line.toUpperCase()
  if (upper.includes('ERROR') || upper.includes('CRITICAL') || upper.includes('FATAL')) return '#f87171'
  if (upper.includes('WARN')) return '#fbbf24'
  if (upper.includes('DEBUG')) return 'rgba(255,255,255,0.3)'
  return undefined
}

export default function LogViewer() {
  const [source, setSource] = useState('tagent')
  const [lines, setLines] = useState<string[]>([])
  const [paused, setPaused] = useState(false)
  const [search, setSearch] = useState('')
  const [showSearch, setShowSearch] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const containerRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const pausedRef = useRef(false)

  useEffect(() => { pausedRef.current = paused }, [paused])

  useEffect(() => {
    setLines([])
    setPaused(false)
    setAutoScroll(true)

    const abort = new AbortController()
    abortRef.current = abort

    const connect = async () => {
      try {
        const res = await fetch(`/api/os/logs/stream?file=${source}&lines=200`, {
          credentials: 'include',
          signal: abort.signal,
        })
        if (!res.ok || !res.body) return
        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const chunks = buffer.split('\n\n')
          buffer = chunks.pop() || ''
          for (const chunk of chunks) {
            const trimmed = chunk.trim()
            if (!trimmed.startsWith('data: ')) continue
            try {
              const event = JSON.parse(trimmed.substring(6))
              if (event.type === 'line' && !pausedRef.current) {
                setLines(prev => [...prev.slice(-2000), event.text])
              }
            } catch {}
          }
        }
      } catch {}
    }
    connect()
    return () => abort.abort()
  }, [source])

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [lines, autoScroll])

  const handleScroll = () => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40)
  }

  const filtered = search
    ? lines.filter(l => l.toLowerCase().includes(search.toLowerCase()))
    : lines

  return (
    <div className="flex flex-col h-full text-sm">
      <div className="flex items-center gap-1 px-2 py-1.5 border-b border-white/[0.06]">
        {LOG_SOURCES.map(s => (
          <button key={s.id} onClick={() => setSource(s.id)}
            className={`px-2.5 py-1 rounded text-xs transition-colors ${source === s.id ? 'bg-white/10 text-white/80' : 'text-white/40 hover:text-white/60 hover:bg-white/5'}`}>
            {s.label}
          </button>
        ))}
        <div className="flex-1" />
        <button onClick={() => setShowSearch(!showSearch)} className={`p-1.5 rounded ${showSearch ? 'bg-white/10' : 'hover:bg-white/5'} text-white/40`}><Search size={13} /></button>
        <button onClick={() => setPaused(!paused)} className={`p-1.5 rounded ${paused ? 'bg-amber-500/20 text-amber-400' : 'hover:bg-white/5 text-white/40'}`}>
          {paused ? <Play size={13} /> : <Pause size={13} />}
        </button>
        {!autoScroll && (
          <button onClick={() => { setAutoScroll(true); if (containerRef.current) containerRef.current.scrollTop = containerRef.current.scrollHeight }} className="p-1.5 rounded hover:bg-white/5 text-white/40"><ArrowDown size={13} /></button>
        )}
        <span className="text-xs text-white/20 ml-1">{lines.length} lines</span>
      </div>
      {showSearch && (
        <div className="flex items-center gap-2 px-2 py-1 border-b border-white/[0.06] bg-white/[0.02]">
          <Search size={12} className="text-white/30" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter logs..." autoFocus className="bg-transparent outline-none flex-1 text-white/70 text-xs placeholder:text-white/20" />
          {search && <button onClick={() => setSearch('')} className="text-white/30 hover:text-white/50"><X size={12} /></button>}
          <span className="text-xs text-white/20">{filtered.length} matches</span>
        </div>
      )}
      <div ref={containerRef} onScroll={handleScroll} className="flex-1 overflow-auto font-mono text-xs leading-5 p-2">
        {filtered.map((line, i) => (
          <div key={i} style={{ color: severityColor(line) || 'rgba(255,255,255,0.55)' }} className="hover:bg-white/[0.02] px-1">
            {search ? highlightSearch(line, search) : line}
          </div>
        ))}
      </div>
    </div>
  )
}

function highlightSearch(text: string, query: string) {
  const idx = text.toLowerCase().indexOf(query.toLowerCase())
  if (idx === -1) return text
  return (
    <>
      {text.slice(0, idx)}
      <span className="bg-amber-500/30 text-amber-200">{text.slice(idx, idx + query.length)}</span>
      {text.slice(idx + query.length)}
    </>
  )
}
