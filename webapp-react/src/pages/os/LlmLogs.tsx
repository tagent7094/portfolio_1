import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Brain, ChevronDown, ChevronRight, RefreshCw, Search } from 'lucide-react'

interface JournalResponse {
  unit: string
  lines: string[]
}

interface LlmEntry {
  timestamp: string
  level: string
  message: string
  provider?: string
  model?: string
  tokens?: number
  latency?: string
  raw: string
}

function parseLlmLogs(lines: string[]): LlmEntry[] {
  const entries: LlmEntry[] = []
  const llmPatterns = [
    /anthropic|openai|ollama|claude|gpt|llm|embed|token|prompt|complet/i,
  ]
  for (const line of lines) {
    if (!llmPatterns.some(p => p.test(line))) continue
    const tsMatch = line.match(/^(\d{4}-\d{2}-\d{2}T[\d:.+]+)\s/)
    const levelMatch = line.match(/\b(ERROR|WARN|WARNING|INFO|DEBUG)\b/i)
    let provider: string | undefined
    if (/anthropic|claude/i.test(line)) provider = 'Anthropic'
    else if (/openai|gpt/i.test(line)) provider = 'OpenAI'
    else if (/ollama/i.test(line)) provider = 'Ollama'
    const modelMatch = line.match(/model[=:]\s*["']?([a-z0-9._-]+)/i)
    const tokenMatch = line.match(/(\d+)\s*tokens?/i)
    const latencyMatch = line.match(/(\d+\.?\d*)\s*(?:ms|sec|s)\b/i)
    entries.push({
      timestamp: tsMatch ? tsMatch[1] : '',
      level: levelMatch ? levelMatch[1].toUpperCase() : 'INFO',
      message: line.slice(tsMatch ? tsMatch[0].length : 0).trim(),
      provider,
      model: modelMatch?.[1],
      tokens: tokenMatch ? parseInt(tokenMatch[1]) : undefined,
      latency: latencyMatch?.[0],
      raw: line,
    })
  }
  return entries
}

export default function LlmLogs() {
  const [entries, setEntries] = useState<LlmEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [search, setSearch] = useState('')
  const [providerFilter, setProviderFilter] = useState<string>('all')
  const [lines, setLines] = useState(500)

  const refresh = async () => {
    setLoading(true)
    try {
      const d = await apiGet<JournalResponse>(`/api/os/logs/journal?unit=tagent&lines=${lines}`)
      setEntries(parseLlmLogs(d.lines))
    } catch {}
    setLoading(false)
  }

  useEffect(() => { refresh() }, [lines])

  const toggle = (i: number) => setExpanded(prev => {
    const next = new Set(prev)
    next.has(i) ? next.delete(i) : next.add(i)
    return next
  })

  const filtered = entries.filter(e => {
    if (providerFilter !== 'all' && e.provider !== providerFilter) return false
    if (search && !e.raw.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  const totalTokens = filtered.reduce((sum, e) => sum + (e.tokens || 0), 0)
  const providers = [...new Set(entries.map(e => e.provider).filter(Boolean))]

  return (
    <div className="flex flex-col h-full text-sm">
      <div className="flex items-center gap-2 p-2 border-b border-white/[0.06]">
        <Brain size={14} className="text-purple-400/60" />
        <div className="flex items-center gap-1.5 flex-1 px-2 py-1 rounded bg-white/5">
          <Search size={12} className="text-white/30" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search LLM logs..." className="bg-transparent outline-none flex-1 text-white/70 text-xs placeholder:text-white/20" />
        </div>
        <select value={providerFilter} onChange={e => setProviderFilter(e.target.value)} className="bg-white/5 text-white/60 rounded px-2 py-1 text-xs border border-white/[0.06]">
          <option value="all">All providers</option>
          {providers.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={lines} onChange={e => setLines(Number(e.target.value))} className="bg-white/5 text-white/60 rounded px-2 py-1 text-xs border border-white/[0.06]">
          <option value={200}>200 lines</option>
          <option value={500}>500 lines</option>
          <option value={1000}>1000 lines</option>
          <option value={2000}>2000 lines</option>
        </select>
        <button onClick={refresh} disabled={loading} className="p-1.5 rounded hover:bg-white/5 text-white/40">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="flex items-center gap-4 px-3 py-1.5 border-b border-white/[0.04] text-xs text-white/30">
        <span>{filtered.length} LLM entries</span>
        {totalTokens > 0 && <span>{totalTokens.toLocaleString()} total tokens</span>}
        {providers.map(p => (
          <span key={p} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{ background: p === 'Anthropic' ? '#d4a574' : p === 'OpenAI' ? '#74b9ff' : '#a29bfe' }} />
            {p}: {entries.filter(e => e.provider === p).length}
          </span>
        ))}
      </div>

      <div className="flex-1 overflow-auto">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-full text-white/20">
            {loading ? 'Loading...' : 'No LLM log entries found'}
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-[#111116]">
              <tr className="text-white/40 text-xs">
                <th className="w-6"></th>
                <th className="text-left px-2 py-1.5 font-medium">Time</th>
                <th className="text-left px-2 py-1.5 font-medium">Provider</th>
                <th className="text-left px-2 py-1.5 font-medium">Model</th>
                <th className="text-right px-2 py-1.5 font-medium">Tokens</th>
                <th className="text-right px-2 py-1.5 font-medium">Latency</th>
                <th className="text-left px-2 py-1.5 font-medium">Message</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e, i) => (
                <>
                  <tr key={i} onClick={() => toggle(i)} className="border-b border-white/[0.03] hover:bg-white/[0.02] cursor-pointer">
                    <td className="px-1 text-white/20">{expanded.has(i) ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</td>
                    <td className="px-2 py-1 font-mono text-xs text-white/40">{e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '-'}</td>
                    <td className="px-2 py-1">
                      {e.provider && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs" style={{
                          background: e.provider === 'Anthropic' ? 'rgba(212,165,116,0.15)' : e.provider === 'OpenAI' ? 'rgba(116,185,255,0.15)' : 'rgba(162,155,254,0.15)',
                          color: e.provider === 'Anthropic' ? '#d4a574' : e.provider === 'OpenAI' ? '#74b9ff' : '#a29bfe',
                        }}>{e.provider}</span>
                      )}
                    </td>
                    <td className="px-2 py-1 font-mono text-xs text-white/50">{e.model || '-'}</td>
                    <td className="px-2 py-1 text-right font-mono text-xs text-white/50">{e.tokens?.toLocaleString() || '-'}</td>
                    <td className="px-2 py-1 text-right font-mono text-xs text-white/40">{e.latency || '-'}</td>
                    <td className="px-2 py-1 text-white/50 truncate max-w-[300px] text-xs">{e.message.slice(0, 120)}</td>
                  </tr>
                  {expanded.has(i) && (
                    <tr key={`${i}-detail`}>
                      <td colSpan={7} className="px-4 py-2 bg-white/[0.02]">
                        <pre className="font-mono text-xs text-white/50 whitespace-pre-wrap break-all">{e.raw}</pre>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
