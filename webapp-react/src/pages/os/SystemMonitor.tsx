import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Activity, HardDrive, Cpu, MemoryStick, Clock } from 'lucide-react'

interface Stats {
  hostname: string
  uptime: string
  load: { '1m': number; '5m': number; '15m': number }
  cpu_percent: number
  memory: { total: number; used: number; percent: number }
  disks: { mount: string; total: number; used: number; available: number; percent: string }[]
}

function formatBytes(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(1)} KB`
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(1)} MB`
  return `${(b / 1024 ** 3).toFixed(1)} GB`
}

function Bar({ percent, color }: { percent: number; color: string }) {
  return (
    <div className="h-3 w-full rounded-full bg-white/5 overflow-hidden">
      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(percent, 100)}%`, background: color }} />
    </div>
  )
}

export default function SystemMonitor() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [history, setHistory] = useState<number[]>([])

  useEffect(() => {
    let active = true
    const poll = async () => {
      try {
        const s = await apiGet<Stats>('/api/os/stats')
        if (active) {
          setStats(s)
          setHistory(h => [...h.slice(-59), s.cpu_percent])
        }
      } catch {}
    }
    poll()
    const iv = setInterval(poll, 3000)
    return () => { active = false; clearInterval(iv) }
  }, [])

  if (!stats) return <div className="flex items-center justify-center h-full text-white/40"><Activity className="animate-spin" size={20} /></div>

  const cpuColor = stats.cpu_percent > 80 ? '#f87171' : stats.cpu_percent > 50 ? '#fbbf24' : '#4ade80'
  const memColor = stats.memory.percent > 80 ? '#f87171' : stats.memory.percent > 50 ? '#fbbf24' : '#4ade80'

  return (
    <div className="p-4 h-full overflow-auto space-y-4 text-sm">
      <div className="flex items-center gap-3 text-white/60">
        <Clock size={14} />
        <span>{stats.hostname}</span>
        <span className="text-white/30">|</span>
        <span>{stats.uptime}</span>
        <span className="text-white/30">|</span>
        <span>Load: {stats.load['1m']} / {stats.load['5m']} / {stats.load['15m']}</span>
      </div>

      {/* CPU */}
      <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 font-medium"><Cpu size={14} /> CPU</div>
          <span style={{ color: cpuColor }} className="font-mono text-lg">{stats.cpu_percent}%</span>
        </div>
        <Bar percent={stats.cpu_percent} color={cpuColor} />
        {history.length > 1 && (
          <div className="mt-3 h-16 flex items-end gap-px">
            {history.map((v, i) => (
              <div key={i} className="flex-1 rounded-t-sm" style={{
                height: `${Math.max(v, 2)}%`,
                background: v > 80 ? '#f87171' : v > 50 ? '#fbbf24' : '#4ade80',
                opacity: 0.6,
              }} />
            ))}
          </div>
        )}
      </div>

      {/* Memory */}
      <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 font-medium"><MemoryStick size={14} /> Memory</div>
          <span style={{ color: memColor }} className="font-mono">{stats.memory.percent}%</span>
        </div>
        <Bar percent={stats.memory.percent} color={memColor} />
        <div className="mt-1 text-xs text-white/40">{formatBytes(stats.memory.used)} / {formatBytes(stats.memory.total)}</div>
      </div>

      {/* Disks */}
      <div className="rounded-lg bg-white/[0.03] border border-white/[0.06] p-4">
        <div className="flex items-center gap-2 font-medium mb-3"><HardDrive size={14} /> Disk</div>
        <div className="space-y-3">
          {stats.disks.map(d => {
            const pct = parseInt(d.percent)
            const dColor = pct > 90 ? '#f87171' : pct > 70 ? '#fbbf24' : '#60a5fa'
            return (
              <div key={d.mount}>
                <div className="flex justify-between text-xs text-white/50 mb-1">
                  <span className="font-mono">{d.mount}</span>
                  <span>{formatBytes(d.used)} / {formatBytes(d.total)} ({d.percent})</span>
                </div>
                <Bar percent={pct} color={dColor} />
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
