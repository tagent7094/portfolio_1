import { useState, useEffect, useMemo } from 'react'
import { Search, MessageCircle, Users, AlertTriangle, ShuffleIcon, Wrench, Award, ThumbsUp, ArrowRight, Loader2, X, ChevronRight } from 'lucide-react'
import ForceGraph from '../components/ForceGraph'
import SankeyFlow from '../components/SankeyFlow'

interface ClientThumb {
  slug: string
  client_name: string
  call_type: string
  pain_count: number
  tool_count: number
  tussle_count: number
  contrarian_count: number
  problem_count: number
  best_count: number
  win_count_immediate: number
  win_count_long_term: number
  has_before_state: boolean
  has_after_state: boolean
}

interface Citation {
  text: string
  client_name: string
  category: string
  speaker: string
  timestamp: string
  summary: string
  quote: string
  source_file: string
  distance: number
}

interface AnswerPayload { answer: string; citations: Citation[] }

const SEVEN_QUESTIONS = [
  { id: 'pain', icon: AlertTriangle, label: 'What problem was each client facing?', q: 'What problems were the clients facing before adopting RevSure?' },
  { id: 'tool', icon: Wrench, label: 'Which tools did they switch from?', q: 'Which tools or vendors did clients switch from to use RevSure, and why?' },
  { id: 'tussle', icon: Users, label: 'Cross-functional political tussles', q: 'What political tussles between CRO, CFO, Sales, and Marketing came up across the calls?' },
  { id: 'contrarian', icon: ShuffleIcon, label: 'Most contrarian things said', q: 'What were the most contrarian things clients said on the calls — opinions that go against the conventional wisdom in revenue ops?' },
  { id: 'problem', icon: AlertTriangle, label: 'Problems with RevSure itself', q: 'What problems did clients run into with RevSure — tool issues, implementation, or understanding?' },
  { id: 'win', icon: Award, label: 'Wins they want to secure', q: 'What wins do clients want to secure with RevSure — both immediate and long-term?' },
  { id: 'best', icon: ThumbsUp, label: 'Best things about RevSure', q: 'What are the best things clients have said about RevSure? Give me their direct quotes.' },
]

const PALETTE = {
  Client: '#a5b4fc', Pain: '#fca5a5', ToolFrom: '#fde68a', Tussle: '#f9a8d4',
  Contrarian: '#d8b4fe', RevSureProblem: '#fdba74', Win: '#86efac',
  BestAspect: '#6ee7b7', Quote: '#94a3b8',
}

export default function AskRevSurePage() {
  const [clients, setClients] = useState<ClientThumb[]>([])
  const [graphData, setGraphData] = useState<{ nodes: any[]; links: any[] } | null>(null)
  const [sankeyData, setSankeyData] = useState<{ nodes: any[]; links: any[] } | null>(null)
  const [query, setQuery] = useState('')
  const [answer, setAnswer] = useState<AnswerPayload | null>(null)
  const [askingId, setAskingId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState('')
  const [selectedClient, setSelectedClient] = useState<string | null>(null)
  const [clientDetail, setClientDetail] = useState<any | null>(null)
  const [clientSort, setClientSort] = useState<'name' | 'wins' | 'problems'>('name')

  useEffect(() => {
    Promise.allSettled([
      fetch('/api/revsure/clients', { credentials: 'include' }).then(r => r.json()),
      fetch('/api/revsure/graph', { credentials: 'include' }).then(r => r.json()),
      fetch('/api/revsure/sankey', { credentials: 'include' }).then(r => r.json()),
    ]).then(([c, g, s]) => {
      if (c.status === 'fulfilled') setClients(c.value.clients || [])
      else setLoadError('Clients list not available — run extraction + graph build first.')
      if (g.status === 'fulfilled') setGraphData(g.value)
      if (s.status === 'fulfilled') setSankeyData(s.value)
    })
  }, [])

  const sortedClients = useMemo(() => {
    const arr = [...clients]
    if (clientSort === 'wins') arr.sort((a, b) =>
      (b.win_count_immediate + b.win_count_long_term) - (a.win_count_immediate + a.win_count_long_term))
    else if (clientSort === 'problems') arr.sort((a, b) => b.problem_count - a.problem_count)
    else arr.sort((a, b) => a.client_name.localeCompare(b.client_name))
    return arr
  }, [clients, clientSort])

  const ask = async (q: string, id: string) => {
    if (!q.trim()) return
    setAskingId(id)
    setAnswer(null)
    try {
      const res = await fetch('/api/revsure/ask', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, n_results: 10 }),
      })
      if (!res.ok) throw new Error(`Request failed: ${res.status}`)
      const data: AnswerPayload = await res.json()
      setAnswer(data)
    } catch (e: any) {
      setAnswer({ answer: `Error: ${e?.message || e}`, citations: [] })
    } finally {
      setAskingId(null)
    }
  }

  const openClient = async (slug: string) => {
    setSelectedClient(slug)
    setClientDetail(null)
    try {
      const res = await fetch(`/api/revsure/client/${slug}`, { credentials: 'include' })
      if (res.ok) setClientDetail(await res.json())
    } catch { /* no-op */ }
  }

  return (
    <div className="min-h-screen bg-[var(--page-bg)] text-[var(--text-primary)]">
      {/* ── Hero ── */}
      <section className="relative">
        <div className="mx-auto max-w-4xl px-5 pb-12 pt-20 text-center">
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-[var(--border-3)] bg-[var(--surface-3)] px-4 py-1.5 text-xs text-[var(--text-muted)]">
            <MessageCircle size={13} />
            Powered by 51 RevSure customer call transcripts
          </div>
          <h1 className="mb-3 text-4xl font-semibold tracking-tight sm:text-5xl">Ask RevSure</h1>
          <p className="mb-7 text-base text-[var(--text-muted)]">
            What customers actually said on calls. Every answer cites verbatim quotes from the transcripts.
          </p>

          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && ask(query, 'custom')}
              placeholder="Ask anything — “Why did Glean switch from Marketo?”"
              className="w-full rounded-2xl border border-[var(--border-3)] bg-[var(--surface-2)] px-5 py-4 pr-14 text-base"
            />
            <button
              onClick={() => ask(query, 'custom')}
              disabled={!query.trim() || askingId !== null}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-xl bg-[var(--accent)] p-2.5 text-[var(--accent-fg)] disabled:opacity-50"
            >
              {askingId === 'custom' ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />}
            </button>
          </div>
        </div>
      </section>

      {/* ── 7 question cards ── */}
      <section className="mx-auto max-w-6xl px-5 pb-10">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-[var(--text-muted)]">The seven questions</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {SEVEN_QUESTIONS.map(({ id, icon: Icon, label, q }) => (
            <button
              key={id}
              onClick={() => ask(q, id)}
              disabled={askingId !== null}
              className="group flex flex-col items-start gap-2 rounded-xl border border-[var(--border-3)] bg-[var(--surface-2)] p-4 text-left transition hover:border-[var(--accent)] disabled:opacity-50"
            >
              <Icon size={18} className="text-[var(--text-muted)] group-hover:text-[var(--accent)]" />
              <div className="text-sm font-medium leading-snug">{label}</div>
              {askingId === id && <Loader2 size={12} className="animate-spin text-[var(--text-muted)]" />}
            </button>
          ))}
        </div>
      </section>

      {/* ── Answer panel ── */}
      {answer && (
        <section className="mx-auto max-w-6xl px-5 pb-12">
          <div className="rounded-2xl border border-[var(--border-3)] bg-[var(--surface-2)] p-6">
            <div className="mb-4 flex items-start justify-between gap-3">
              <h3 className="text-base font-medium">Answer</h3>
              <button onClick={() => setAnswer(null)} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">
                <X size={14} />
              </button>
            </div>
            <div className="prose prose-invert prose-sm max-w-none whitespace-pre-wrap leading-relaxed text-[var(--text-primary)]">
              {answer.answer}
            </div>
            {answer.citations.length > 0 && (
              <div className="mt-6 border-t border-[var(--border-3)] pt-5">
                <h4 className="mb-3 text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
                  Direct citations ({answer.citations.length})
                </h4>
                <div className="space-y-3">
                  {answer.citations.map((c, i) => (
                    <div key={i} className="rounded-lg border border-[var(--border-3)] bg-[var(--surface-3)] p-3 text-sm">
                      <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
                        <span className="rounded bg-[var(--surface-2)] px-2 py-0.5 font-mono">[{i + 1}]</span>
                        <span className="font-medium text-[var(--text-primary)]">{c.client_name}</span>
                        <span>·</span>
                        <span>{c.speaker} @ {c.timestamp}</span>
                        <span className="rounded-full bg-[var(--accent)]/15 px-2 py-0.5 text-[var(--accent)]">
                          {c.category}
                        </span>
                      </div>
                      <p className="italic text-[var(--text-primary)]">"{c.quote}"</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ── Per-client journey carousel ── */}
      <section className="mx-auto max-w-6xl px-5 pb-12">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--text-muted)]">Per-client journey</h2>
            <p className="mt-1 text-xs text-[var(--text-muted)]">Before → After for each of {clients.length} customers.</p>
          </div>
          <div className="flex gap-1 text-xs">
            {(['name', 'wins', 'problems'] as const).map(s => (
              <button
                key={s}
                onClick={() => setClientSort(s)}
                className={`rounded px-2 py-1 ${clientSort === s ? 'bg-[var(--accent)] text-[var(--accent-fg)]' : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'}`}
              >
                Sort: {s}
              </button>
            ))}
          </div>
        </div>

        {loadError && <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-300">{loadError}</div>}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sortedClients.map(c => (
            <button
              key={c.slug}
              onClick={() => openClient(c.slug)}
              className="group flex flex-col gap-2 rounded-xl border border-[var(--border-3)] bg-[var(--surface-2)] p-4 text-left transition hover:border-[var(--accent)]"
            >
              <div className="flex items-center justify-between">
                <h3 className="font-medium">{c.client_name}</h3>
                <ChevronRight size={14} className="text-[var(--text-muted)] group-hover:text-[var(--accent)]" />
              </div>
              <div className="flex flex-wrap gap-1.5 text-xs text-[var(--text-muted)]">
                {c.pain_count > 0 && <span className="rounded bg-red-500/15 px-1.5 py-0.5 text-red-300">{c.pain_count} pains</span>}
                {c.tool_count > 0 && <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-amber-300">{c.tool_count} switched</span>}
                {(c.win_count_immediate + c.win_count_long_term) > 0 && <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-emerald-300">{c.win_count_immediate + c.win_count_long_term} wins</span>}
                {c.problem_count > 0 && <span className="rounded bg-orange-500/15 px-1.5 py-0.5 text-orange-300">{c.problem_count} problems</span>}
                {c.contrarian_count > 0 && <span className="rounded bg-purple-500/15 px-1.5 py-0.5 text-purple-300">{c.contrarian_count} contrarian</span>}
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* ── Global Sankey ── */}
      <section className="mx-auto max-w-6xl px-5 pb-12">
        <h2 className="mb-1 text-sm font-medium uppercase tracking-wide text-[var(--text-muted)]">Journey overview</h2>
        <p className="mb-4 text-xs text-[var(--text-muted)]">
          Aggregate flow across all customers: tools they switched from → pains they hit → wins they secured with RevSure.
        </p>
        <div className="rounded-2xl border border-[var(--border-3)] bg-[var(--surface-2)] p-3">
          {sankeyData ? (
            <SankeyFlow nodes={sankeyData.nodes} links={sankeyData.links} height={460} />
          ) : (
            <div className="flex h-[460px] items-center justify-center text-sm text-[var(--text-muted)]">
              Sankey data loading…
            </div>
          )}
        </div>
      </section>

      {/* ── Global Force Graph ── */}
      <section className="mx-auto max-w-6xl px-5 pb-16">
        <h2 className="mb-1 text-sm font-medium uppercase tracking-wide text-[var(--text-muted)]">Knowledge graph explorer</h2>
        <p className="mb-4 text-xs text-[var(--text-muted)]">
          Every claim from every call, linked to its source quote. Click a node to drill in.
        </p>
        <div className="rounded-2xl border border-[var(--border-3)] bg-[var(--surface-2)] p-3">
          {graphData ? (
            <ForceGraph
              nodes={graphData.nodes}
              links={graphData.links}
              height={640}
              palette={PALETTE}
            />
          ) : (
            <div className="flex h-[640px] items-center justify-center text-sm text-[var(--text-muted)]">
              Graph loading…
            </div>
          )}
        </div>
      </section>

      {/* ── Client detail drawer ── */}
      {selectedClient && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 sm:items-center" onClick={() => setSelectedClient(null)}>
          <div
            onClick={(e) => e.stopPropagation()}
            className="max-h-[85vh] w-full max-w-4xl overflow-y-auto rounded-t-2xl border border-[var(--border-3)] bg-[var(--surface-2)] p-6 sm:rounded-2xl"
          >
            {!clientDetail ? (
              <div className="flex items-center gap-2 text-[var(--text-muted)]">
                <Loader2 size={16} className="animate-spin" />
                Loading client detail…
              </div>
            ) : (
              <ClientDetailPanel detail={clientDetail} onClose={() => setSelectedClient(null)} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Per-client Before/After panel ──

function ClientDetailPanel({ detail, onClose }: { detail: any; onClose: () => void }) {
  const before = detail.before_state || {}
  const after = detail.after_state || {}
  const f = detail.findings || {}
  const wins = f.wins || {}
  return (
    <div>
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-2xl font-semibold tracking-tight">{detail.client_name}</h3>
          <p className="mt-0.5 text-sm text-[var(--text-muted)]">
            {detail.call_type} · {(detail._meta?.source_files || []).length} source file(s)
          </p>
        </div>
        <button onClick={onClose} className="text-[var(--text-muted)] hover:text-[var(--text-primary)]">
          <X size={18} />
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {/* Before */}
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
          <h4 className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-amber-300">
            <ArrowRight size={12} />
            Before RevSure
          </h4>
          {before.pain_summary && <p className="mb-3 text-sm italic">"{before.pain_summary}"</p>}
          {(before.stack || []).length > 0 && (
            <div className="mb-3">
              <div className="mb-1 text-xs text-[var(--text-muted)]">Stack</div>
              <div className="flex flex-wrap gap-1">
                {before.stack.map((s: string, i: number) => (
                  <span key={i} className="rounded bg-[var(--surface-3)] px-1.5 py-0.5 text-xs">{s}</span>
                ))}
              </div>
            </div>
          )}
          {(before.kpis_unhealthy || []).length > 0 && (
            <div>
              <div className="mb-1 text-xs text-[var(--text-muted)]">Unhealthy KPIs</div>
              <ul className="list-inside list-disc text-sm text-[var(--text-muted)]">
                {before.kpis_unhealthy.map((k: string, i: number) => <li key={i}>{k}</li>)}
              </ul>
            </div>
          )}
        </div>

        {/* After */}
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
          <h4 className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-emerald-300">
            <ArrowRight size={12} />
            After RevSure
          </h4>
          {after.with_revsure && <p className="mb-3 text-sm italic">"{after.with_revsure}"</p>}
          {(after.wins_realized || []).length > 0 && (
            <div className="mb-3">
              <div className="mb-1 text-xs text-[var(--text-muted)]">Wins realized</div>
              <ul className="list-inside list-disc text-sm">
                {after.wins_realized.map((w: string, i: number) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}
          {(after.open_issues || []).length > 0 && (
            <div>
              <div className="mb-1 text-xs text-[var(--text-muted)]">Open issues</div>
              <ul className="list-inside list-disc text-sm text-[var(--text-muted)]">
                {after.open_issues.map((o: string, i: number) => <li key={i}>{o}</li>)}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Findings detail */}
      <div className="mt-6 space-y-4">
        <FindingsBlock title="Pains" items={f.pains || []} color="red" labelField="summary" />
        <FindingsBlock title="Tools switched from" items={f.tools_switched_from || []} color="amber" labelField="tool" extra={(i: any) => i.vendor ? ` (${i.vendor})` : ''} />
        <FindingsBlock title="Political tussles" items={f.political_tussles || []} color="pink" labelField="tension_label" extra={(i: any) => (i.actors || []).length ? ` — ${(i.actors || []).join(' ↔ ')}` : ''} />
        <FindingsBlock title="Contrarian claims" items={f.contrarians || []} color="purple" labelField="claim" />
        <FindingsBlock title="Problems with RevSure" items={f.revsure_problems || []} color="orange" labelField="problem" extra={(i: any) => i.category ? ` [${i.category}]` : ''} />
        <FindingsBlock title="Wins — immediate" items={wins.immediate || []} color="emerald" labelField="win" />
        <FindingsBlock title="Wins — long term" items={wins.long_term || []} color="emerald" labelField="win" />
        <FindingsBlock title="Best about RevSure" items={f.best_about_revsure || []} color="cyan" labelField="summary" />
      </div>
    </div>
  )
}

function FindingsBlock({
  title, items, color, labelField, extra,
}: { title: string; items: any[]; color: string; labelField: string; extra?: (i: any) => string }) {
  if (!items.length) return null
  const colorMap: Record<string, string> = {
    red: 'border-red-500/30 bg-red-500/5',
    amber: 'border-amber-500/30 bg-amber-500/5',
    pink: 'border-pink-500/30 bg-pink-500/5',
    purple: 'border-purple-500/30 bg-purple-500/5',
    orange: 'border-orange-500/30 bg-orange-500/5',
    emerald: 'border-emerald-500/30 bg-emerald-500/5',
    cyan: 'border-cyan-500/30 bg-cyan-500/5',
  }
  return (
    <div className={`rounded-xl border ${colorMap[color] || 'border-[var(--border-3)]'} p-4`}>
      <h4 className="mb-2 text-xs font-medium uppercase tracking-wide opacity-80">{title} ({items.length})</h4>
      <div className="space-y-3">
        {items.map((it, i) => (
          <div key={i} className="text-sm">
            <div className="font-medium">{it[labelField]}{extra ? extra(it) : ''}</div>
            {it.quote && (
              <p className="mt-1 italic text-[var(--text-muted)]">
                "{it.quote}" <span className="text-[10px] opacity-70">— {it.speaker || 'unknown'} @ {it.timestamp || '?'}</span>
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
