import { useState, useMemo } from 'react'
import {
  ChevronDown, ChevronRight, Cpu, Search, GitBranch,
  Clock, Zap, Globe, FileText,
} from 'lucide-react'
import clsx from 'clsx'

interface TraceEntry {
  id: string
  timestamp: number
  type: 'llm_call' | 'web_search' | 'decision' | 'step'
  stage: string
  template?: string
  prompt_preview?: string
  prompt_length?: number
  response_preview?: string
  response_length?: number
  thinking_preview?: string
  thinking_length?: number
  temperature?: number
  max_tokens?: number
  model?: string
  provider?: string
  duration_ms?: number
  search_query?: string
  search_results?: Array<{ url: string; title: string; page_age?: string }>
  decision?: string
  metadata?: Record<string, any>
}

interface TraceSummary {
  total_traces: number
  llm_calls: number
  web_searches: number
  decisions: number
  total_duration_ms: number
  total_prompt_chars: number
  total_response_chars: number
  templates_used: string[]
  model: string
  provider: string
}

interface TraceData {
  summary?: TraceSummary
  traces?: TraceEntry[]
}

interface WebSearchData {
  trending_topics?: string[]
  facts?: Array<{ fact: string; source: string; relevance: string }>
  contrarian_angles?: string[]
  searches_performed?: Array<{ query: string; results?: Array<{ url: string; title: string }> }>
}

interface Props {
  traceability?: TraceData
  webSearch?: WebSearchData
  className?: string
}

const TYPE_ICON: Record<string, typeof Cpu> = {
  llm_call: Cpu,
  web_search: Globe,
  decision: GitBranch,
  step: Zap,
}

const TYPE_COLOR: Record<string, string> = {
  llm_call: 'text-violet-400',
  web_search: 'text-sky-400',
  decision: 'text-amber-400',
  step: 'text-emerald-400',
}

const TYPE_BG: Record<string, string> = {
  llm_call: 'bg-violet-950/40 border-violet-800/30',
  web_search: 'bg-sky-950/40 border-sky-800/30',
  decision: 'bg-amber-950/40 border-amber-800/30',
  step: 'bg-emerald-950/40 border-emerald-800/30',
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}m`
}

function formatChars(n: number): string {
  if (n < 1000) return `${n}`
  return `${(n / 1000).toFixed(1)}k`
}

function TraceEntryRow({ entry }: { entry: TraceEntry }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = TYPE_ICON[entry.type] || Zap
  const color = TYPE_COLOR[entry.type] || 'text-white/50'
  const bg = TYPE_BG[entry.type] || ''

  return (
    <div className={clsx('rounded-lg border transition-colors', bg)}>
      <button
        onClick={() => setExpanded(e => !e)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        {expanded ? <ChevronDown size={11} className="shrink-0 text-white/30" /> :
          <ChevronRight size={11} className="shrink-0 text-white/30" />}
        <Icon size={12} className={clsx('shrink-0', color)} />
        <span className="flex-1 truncate text-[11px] text-white/70">{entry.stage}</span>
        {entry.template && (
          <span className="hidden sm:inline rounded bg-white/5 px-1.5 py-0.5 text-[9px] font-mono text-white/40">
            {entry.template}
          </span>
        )}
        {entry.search_query && (
          <span className="hidden sm:inline rounded bg-sky-500/10 px-1.5 py-0.5 text-[9px] text-sky-400">
            "{entry.search_query}"
          </span>
        )}
        {entry.duration_ms != null && entry.duration_ms > 0 && (
          <span className="text-[10px] font-mono text-white/30">
            {formatDuration(entry.duration_ms)}
          </span>
        )}
      </button>

      {expanded && (
        <div className="border-t border-white/5 px-3 py-2 space-y-2">
          {/* Meta row */}
          <div className="flex flex-wrap gap-3 text-[10px] text-white/40">
            {entry.model && <span>model: {entry.model}</span>}
            {entry.temperature != null && entry.temperature > 0 && <span>temp: {entry.temperature}</span>}
            {entry.max_tokens != null && entry.max_tokens > 0 && <span>max_tokens: {entry.max_tokens}</span>}
            {entry.prompt_length != null && entry.prompt_length > 0 && <span>prompt: {formatChars(entry.prompt_length)} chars</span>}
            {entry.thinking_length != null && entry.thinking_length > 0 && <span className="text-amber-400/40">thinking: {formatChars(entry.thinking_length)} chars</span>}
            {entry.response_length != null && entry.response_length > 0 && <span>response: {formatChars(entry.response_length)} chars</span>}
          </div>

          {/* Prompt preview */}
          {entry.prompt_preview && (
            <div>
              <div className="mb-1 text-[9px] font-semibold uppercase tracking-widest text-white/30">Prompt</div>
              <pre className="max-h-[200px] overflow-auto rounded-md bg-black/30 p-2 text-[10px] leading-relaxed text-white/60 whitespace-pre-wrap">
                {entry.prompt_preview}
                {entry.prompt_length && entry.prompt_length > 500 && (
                  <span className="text-white/20">{'\n'}...({formatChars(entry.prompt_length)} total)</span>
                )}
              </pre>
            </div>
          )}

          {/* Thinking preview */}
          {entry.thinking_preview && (
            <div>
              <div className="mb-1 text-[9px] font-semibold uppercase tracking-widest text-amber-400/50">Thinking</div>
              <pre className="max-h-[200px] overflow-auto rounded-md bg-amber-950/20 border border-amber-800/20 p-2 text-[10px] leading-relaxed text-amber-200/50 whitespace-pre-wrap italic">
                {entry.thinking_preview}
                {entry.thinking_length && entry.thinking_length > 1000 && (
                  <span className="text-amber-400/20">{'\n'}...({formatChars(entry.thinking_length)} total)</span>
                )}
              </pre>
            </div>
          )}

          {/* Response preview */}
          {entry.response_preview && (
            <div>
              <div className="mb-1 text-[9px] font-semibold uppercase tracking-widest text-white/30">Response</div>
              <pre className="max-h-[200px] overflow-auto rounded-md bg-black/30 p-2 text-[10px] leading-relaxed text-white/60 whitespace-pre-wrap">
                {entry.response_preview}
                {entry.response_length && entry.response_length > 500 && (
                  <span className="text-white/20">{'\n'}...({formatChars(entry.response_length)} total)</span>
                )}
              </pre>
            </div>
          )}

          {/* Decision */}
          {entry.decision && (
            <div className="text-[11px] text-white/60">
              {entry.decision}
            </div>
          )}

          {/* Search results */}
          {entry.search_results && entry.search_results.length > 0 && (
            <div>
              <div className="mb-1 text-[9px] font-semibold uppercase tracking-widest text-white/30">Search Results</div>
              <div className="space-y-1">
                {entry.search_results.map((r, i) => (
                  <div key={i} className="flex items-start gap-2 text-[10px]">
                    <Globe size={10} className="mt-0.5 shrink-0 text-sky-400/50" />
                    <div>
                      <a href={r.url} target="_blank" rel="noopener noreferrer" className="text-sky-400/70 hover:text-sky-400">
                        {r.title || r.url}
                      </a>
                      {r.page_age && <span className="ml-2 text-white/20">{r.page_age}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Metadata */}
          {entry.metadata && Object.keys(entry.metadata).length > 0 && (
            <div className="text-[10px] text-white/30 font-mono">
              {Object.entries(entry.metadata).map(([k, v]) => (
                <span key={k} className="mr-3">{k}={JSON.stringify(v)}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function TraceViewer({ traceability, webSearch, className }: Props) {
  const [filter, setFilter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')

  const traces = traceability?.traces || []
  const summary = traceability?.summary

  const filtered = useMemo(() => {
    let items = traces
    if (filter !== 'all') items = items.filter(t => t.type === filter)
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      items = items.filter(t =>
        t.stage.toLowerCase().includes(q) ||
        (t.template || '').toLowerCase().includes(q) ||
        (t.prompt_preview || '').toLowerCase().includes(q) ||
        (t.search_query || '').toLowerCase().includes(q)
      )
    }
    return items
  }, [traces, filter, searchQuery])

  if (!traceability && !webSearch) {
    return null
  }

  return (
    <div className={clsx('space-y-4', className)}>
      {/* Summary stats */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[
            { label: 'LLM Calls', value: summary.llm_calls, icon: Cpu, color: 'text-violet-400' },
            { label: 'Web Searches', value: summary.web_searches, icon: Globe, color: 'text-sky-400' },
            { label: 'Decisions', value: summary.decisions, icon: GitBranch, color: 'text-amber-400' },
            { label: 'Total Time', value: formatDuration(summary.total_duration_ms), icon: Clock, color: 'text-white/50' },
          ].map(s => (
            <div key={s.label} className="rounded-lg border border-white/5 bg-white/[0.02] p-2.5">
              <div className="flex items-center gap-1.5">
                <s.icon size={11} className={s.color} />
                <span className="text-[10px] text-white/40">{s.label}</span>
              </div>
              <div className="mt-1 text-[15px] font-semibold text-white/80">{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Templates used */}
      {summary && summary.templates_used.length > 0 && (
        <div className="flex flex-wrap gap-1">
          <FileText size={10} className="mt-1 text-white/20" />
          {summary.templates_used.map(t => (
            <span key={t} className="rounded bg-white/5 px-1.5 py-0.5 text-[9px] font-mono text-white/40">
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Web search findings */}
      {webSearch && (webSearch.trending_topics?.length || webSearch.facts?.length) ? (
        <div className="rounded-lg border border-sky-800/30 bg-sky-950/30 p-3 space-y-2">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-sky-400">
            <Globe size={12} /> Web Search Findings
          </div>
          {webSearch.trending_topics && webSearch.trending_topics.length > 0 && (
            <div>
              <div className="text-[9px] uppercase tracking-widest text-sky-400/50 mb-1">Trending Topics</div>
              <div className="flex flex-wrap gap-1">
                {webSearch.trending_topics.map((t, i) => (
                  <span key={i} className="rounded-full bg-sky-500/10 px-2 py-0.5 text-[10px] text-sky-300">{t}</span>
                ))}
              </div>
            </div>
          )}
          {webSearch.facts && webSearch.facts.length > 0 && (
            <div>
              <div className="text-[9px] uppercase tracking-widest text-sky-400/50 mb-1">Facts Found</div>
              <div className="space-y-1">
                {webSearch.facts.map((f, i) => (
                  <div key={i} className="text-[10px] text-sky-200/60">
                    <span className="text-sky-300/80">{f.fact}</span>
                    {f.source && <span className="ml-1 text-sky-400/30">— {f.source}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : null}

      {/* Filter bar */}
      {traces.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex rounded-lg border border-white/5 overflow-hidden text-[10px]">
            {['all', 'llm_call', 'web_search', 'decision', 'step'].map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={clsx(
                  'px-2.5 py-1.5 transition-colors',
                  filter === f ? 'bg-white/10 text-white/80' : 'text-white/30 hover:text-white/50'
                )}
              >
                {f === 'all' ? `All (${traces.length})` :
                  f === 'llm_call' ? `LLM (${traces.filter(t => t.type === 'llm_call').length})` :
                    f === 'web_search' ? `Search (${traces.filter(t => t.type === 'web_search').length})` :
                      f === 'decision' ? `Decisions (${traces.filter(t => t.type === 'decision').length})` :
                        `Steps (${traces.filter(t => t.type === 'step').length})`}
              </button>
            ))}
          </div>
          <div className="relative flex-1 min-w-[120px] max-w-[250px]">
            <Search size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-white/20" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Filter traces..."
              className="w-full rounded-lg border border-white/5 bg-white/[0.02] pl-7 pr-2 py-1.5 text-[10px] text-white/70 placeholder:text-white/20 focus:outline-none"
            />
          </div>
        </div>
      )}

      {/* Trace entries */}
      {filtered.length > 0 && (
        <div className="space-y-1 max-h-[500px] overflow-y-auto">
          {filtered.map(entry => (
            <TraceEntryRow key={entry.id} entry={entry} />
          ))}
        </div>
      )}

      {traces.length > 0 && filtered.length === 0 && (
        <div className="text-center py-6 text-[11px] text-white/30">
          No traces match the current filter
        </div>
      )}
    </div>
  )
}
