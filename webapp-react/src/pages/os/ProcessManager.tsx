import { useEffect, useState, useMemo } from 'react'
import { apiGet, apiPost } from '../../api/client'
import { Search, Skull, RefreshCw } from 'lucide-react'

interface Process {
  user: string
  pid: number
  cpu: number
  mem: number
  rss: number
  stat: string
  command: string
}

function formatKB(kb: number) {
  if (kb < 1024) return `${kb} KB`
  return `${(kb / 1024).toFixed(1)} MB`
}

export default function ProcessManager() {
  const [procs, setProcs] = useState<Process[]>([])
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<'mem' | 'cpu' | 'pid'>('mem')
  const [killing, setKilling] = useState<number | null>(null)

  const refresh = async () => {
    try {
      const d = await apiGet<{ processes: Process[] }>('/api/os/processes')
      setProcs(d.processes)
    } catch {}
  }

  useEffect(() => {
    refresh()
    const iv = setInterval(refresh, 5000)
    return () => clearInterval(iv)
  }, [])

  const filtered = useMemo(() => {
    let list = procs
    if (search) {
      const q = search.toLowerCase()
      list = list.filter(p => p.command.toLowerCase().includes(q) || p.user.toLowerCase().includes(q) || String(p.pid).includes(q))
    }
    return [...list].sort((a, b) => sort === 'cpu' ? b.cpu - a.cpu : sort === 'pid' ? a.pid - b.pid : b.mem - a.mem)
  }, [procs, search, sort])

  const kill = async (pid: number) => {
    if (!confirm(`Kill PID ${pid}?`)) return
    setKilling(pid)
    try {
      await apiPost(`/api/os/processes/${pid}/kill`, { signal: 'TERM' })
      setTimeout(refresh, 500)
    } catch {}
    setKilling(null)
  }

  return (
    <div className="flex flex-col h-full text-sm">
      <div className="flex items-center gap-2 p-2 border-b border-white/[0.06]">
        <div className="flex items-center gap-1.5 flex-1 px-2 py-1 rounded bg-white/5">
          <Search size={13} className="text-white/30" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter processes..." className="bg-transparent outline-none flex-1 text-white/80 placeholder:text-white/20" />
        </div>
        <button onClick={refresh} className="p-1.5 rounded hover:bg-white/5 text-white/40"><RefreshCw size={14} /></button>
        <select value={sort} onChange={e => setSort(e.target.value as any)} className="bg-white/5 text-white/60 rounded px-2 py-1 text-xs border border-white/[0.06]">
          <option value="mem">Sort: Memory</option>
          <option value="cpu">Sort: CPU</option>
          <option value="pid">Sort: PID</option>
        </select>
        <span className="text-xs text-white/30">{filtered.length} procs</span>
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-[#111116]">
            <tr className="text-white/40 text-xs">
              <th className="text-left px-2 py-1.5 font-medium">PID</th>
              <th className="text-left px-2 py-1.5 font-medium">User</th>
              <th className="text-right px-2 py-1.5 font-medium">CPU%</th>
              <th className="text-right px-2 py-1.5 font-medium">MEM%</th>
              <th className="text-right px-2 py-1.5 font-medium">RSS</th>
              <th className="text-left px-2 py-1.5 font-medium">Command</th>
              <th className="w-8"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 200).map(p => (
              <tr key={p.pid} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                <td className="px-2 py-1 font-mono text-white/50">{p.pid}</td>
                <td className="px-2 py-1 text-white/50">{p.user}</td>
                <td className="px-2 py-1 text-right font-mono" style={{ color: p.cpu > 50 ? '#f87171' : p.cpu > 10 ? '#fbbf24' : 'rgba(255,255,255,0.5)' }}>{p.cpu.toFixed(1)}</td>
                <td className="px-2 py-1 text-right font-mono" style={{ color: p.mem > 20 ? '#f87171' : p.mem > 5 ? '#fbbf24' : 'rgba(255,255,255,0.5)' }}>{p.mem.toFixed(1)}</td>
                <td className="px-2 py-1 text-right text-white/40 font-mono text-xs">{formatKB(p.rss)}</td>
                <td className="px-2 py-1 text-white/60 truncate max-w-[300px] font-mono text-xs">{p.command}</td>
                <td className="px-1">
                  <button onClick={() => kill(p.pid)} disabled={killing === p.pid} className="p-1 rounded hover:bg-red-500/20 text-white/20 hover:text-red-400 disabled:opacity-30">
                    <Skull size={12} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
