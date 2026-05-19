import { useState, useEffect, useMemo } from 'react'
import { Loader2, X } from 'lucide-react'
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

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII']
const DISPATCHES = [
  {
    id: 'pain',
    kicker: 'The Pain',
    head: 'What was broken before they called RevSure.',
    deck: 'Pipeline visibility gaps, attribution arguments, KPIs that never aligned — the structural pains that brought every customer to the table.',
    q: 'What problems were the clients facing before adopting RevSure?',
  },
  {
    id: 'tool',
    kicker: 'The Switch',
    head: 'Which vendors got sunset, and why.',
    deck: 'Marketo, Salesforce reports, Tableau dashboards, homegrown spreadsheets — the tools customers walked away from to consolidate on RevSure.',
    q: 'Which tools or vendors did clients switch from to use RevSure, and why?',
  },
  {
    id: 'tussle',
    kicker: 'The Tussle',
    head: 'CRO vs CFO vs Sales vs Marketing.',
    deck: 'Where org-chart politics surfaced on the calls — the moments executives openly disagreed about who owns pipeline truth.',
    q: 'What political tussles between CRO, CFO, Sales, and Marketing came up across the calls?',
  },
  {
    id: 'contrarian',
    kicker: 'The Contrarian',
    head: 'Things they said you’re not supposed to say.',
    deck: 'Opinions that cut against the conventional revenue-ops wisdom — the heretical claims customers actually made on record.',
    q: 'What were the most contrarian things clients said on the calls — opinions that go against the conventional wisdom in revenue ops?',
  },
  {
    id: 'problem',
    kicker: 'The Friction',
    head: 'Problems with RevSure itself.',
    deck: 'Implementation snags, integration gaps, UX miscues, conceptual misunderstandings — what the product still owes its customers.',
    q: 'What problems did clients run into with RevSure — tool issues, implementation, or understanding?',
  },
  {
    id: 'win',
    kicker: 'The Win',
    head: 'What they came here to secure.',
    deck: 'Immediate wins booked in week one, and the long-tail wins they’re still working toward. Both, with the words they used.',
    q: 'What wins do clients want to secure with RevSure — both immediate and long-term?',
  },
  {
    id: 'best',
    kicker: 'The Praise',
    head: 'The unprompted compliments.',
    deck: 'Lines customers volunteered without being asked — the moments the call drifted into testimonial territory.',
    q: 'What are the best things clients have said about RevSure? Give me their direct quotes.',
  },
]

const PALETTE = {
  Client: '#e7c9a3', Pain: '#e85d3c', ToolFrom: '#c89455', Tussle: '#b06c8a',
  Contrarian: '#a679b4', RevSureProblem: '#d97a3a', Win: '#8aa67a',
  BestAspect: '#9bbf99', Quote: '#7a7568',
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
    const safeFetch = async (url: string) => {
      const r = await fetch(url, { credentials: 'include' })
      if (!r.ok) return { _error: r.status, _detail: (await r.json().catch(() => null))?.detail }
      return await r.json()
    }
    Promise.allSettled([
      safeFetch('/api/revsure/clients'),
      safeFetch('/api/revsure/graph'),
      safeFetch('/api/revsure/sankey'),
    ]).then(([c, g, s]) => {
      const cv = c.status === 'fulfilled' ? c.value : null
      const gv = g.status === 'fulfilled' ? g.value : null
      const sv = s.status === 'fulfilled' ? s.value : null

      if (cv && Array.isArray(cv.clients)) {
        setClients(cv.clients)
      } else {
        setLoadError(
          (cv?._detail || gv?._detail || sv?._detail)
          || 'Dossier index loading — extraction pipeline is mid-run.',
        )
      }
      if (gv && Array.isArray(gv.nodes) && Array.isArray(gv.links)) setGraphData(gv)
      if (sv && Array.isArray(sv.nodes) && Array.isArray(sv.links)) setSankeyData(sv)
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

  const stats = useMemo(() => {
    const totalPain = clients.reduce((a, c) => a + c.pain_count, 0)
    const totalWin = clients.reduce((a, c) => a + c.win_count_immediate + c.win_count_long_term, 0)
    const totalProblem = clients.reduce((a, c) => a + c.problem_count, 0)
    const totalContrarian = clients.reduce((a, c) => a + c.contrarian_count, 0)
    return {
      clients: clients.length,
      pains: totalPain,
      wins: totalWin,
      problems: totalProblem,
      contrarians: totalContrarian,
      nodes: graphData?.nodes?.length ?? 0,
      quotes: graphData?.nodes?.filter((n: any) => n.node_type === 'Quote').length ?? 0,
    }
  }, [clients, graphData])

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
      requestAnimationFrame(() => {
        document.getElementById('answer-anchor')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      })
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

  const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }).toUpperCase()

  return (
    <div className="revsure-root">
      <ScopedStyles />

      {/* ── MASTHEAD ── */}
      <header className="rs-masthead">
        <div className="rs-rule rs-rule-top" aria-hidden />
        <div className="rs-masthead-row">
          <div className="rs-issue">VOL. I · NO. 01</div>
          <div className="rs-date">{today}</div>
          <div className="rs-tagline">A Customer-Intelligence Brief</div>
        </div>
        <div className="rs-rule rs-rule-double" aria-hidden />

        <h1 className="rs-title">
          <span className="rs-title-ask">Ask</span>
          <span className="rs-title-rev">RevSure</span>
        </h1>

        <div className="rs-rule rs-rule-thin" aria-hidden />

        <p className="rs-standfirst">
          What <em>twenty-eight</em> customers actually said on the calls — every claim
          tied back to the speaker, the timestamp and the verbatim quote. No paraphrase.
          No spin. Just the transcript, indexed.
        </p>

        <div className="rs-search">
          <span className="rs-search-prompt">Ask.</span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && ask(query, 'custom')}
            placeholder="Why did Glean walk away from Marketo?"
            className="rs-search-input"
          />
          <button
            onClick={() => ask(query, 'custom')}
            disabled={!query.trim() || askingId !== null}
            className="rs-search-btn"
          >
            {askingId === 'custom' ? <Loader2 size={14} className="rs-spin" /> : <span>→</span>}
          </button>
        </div>
      </header>

      {/* ── BY THE NUMBERS ── */}
      <section className="rs-numbers">
        <div className="rs-kicker">By the Numbers</div>
        <div className="rs-numbers-grid">
          <Stat n={stats.clients} l="Customers" />
          <Stat n={stats.pains} l="Pains documented" />
          <Stat n={stats.wins} l="Wins recorded" />
          <Stat n={stats.contrarians} l="Contrarian claims" />
          <Stat n={stats.problems} l="Friction points" />
          <Stat n={stats.quotes} l="Verbatim quotes" />
        </div>
      </section>

      {/* ── ANSWER ANCHOR + DRAWER ── */}
      <div id="answer-anchor" />
      {answer && (
        <section className="rs-answer">
          <div className="rs-kicker rs-kicker-accent">Dispatch in Reply</div>
          <button onClick={() => setAnswer(null)} className="rs-answer-close" aria-label="Close">
            <X size={16} />
          </button>
          <div className="rs-answer-body">{answer.answer}</div>
          {answer.citations.length > 0 && (
            <>
              <div className="rs-rule rs-rule-thin rs-mt-32" aria-hidden />
              <div className="rs-citations-head">
                Sources <span className="rs-mono-small">({answer.citations.length})</span>
              </div>
              <ol className="rs-citations">
                {answer.citations.map((c, i) => (
                  <li key={i} className="rs-citation">
                    <span className="rs-citation-num">{String(i + 1).padStart(2, '0')}</span>
                    <div className="rs-citation-body">
                      <div className="rs-citation-meta">
                        <span className="rs-citation-client">{c.client_name}</span>
                        <span className="rs-dot">·</span>
                        <span className="rs-citation-cat">{c.category}</span>
                        <span className="rs-dot">·</span>
                        <span className="rs-mono-small">{c.speaker || 'unknown'}</span>
                        <span className="rs-mono-small rs-dim">@ {c.timestamp || '—'}</span>
                      </div>
                      <blockquote className="rs-citation-quote">“{c.quote}”</blockquote>
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}
        </section>
      )}

      {/* ── DISPATCHES ── */}
      <section className="rs-dispatches">
        <div className="rs-section-head">
          <div className="rs-section-label">§ The Seven Dispatches</div>
          <div className="rs-section-rule" aria-hidden />
          <div className="rs-section-meta">Click any dispatch to file its question.</div>
        </div>

        <ol className="rs-dispatch-list">
          {DISPATCHES.map((d, i) => (
            <li key={d.id} className="rs-dispatch">
              <button
                onClick={() => ask(d.q, d.id)}
                disabled={askingId !== null}
                className="rs-dispatch-btn"
              >
                <span className="rs-dispatch-num">{ROMAN[i]}.</span>
                <div className="rs-dispatch-body">
                  <div className="rs-dispatch-kicker">{d.kicker}</div>
                  <div className="rs-dispatch-head">{d.head}</div>
                  <div className="rs-dispatch-deck">{d.deck}</div>
                </div>
                <span className="rs-dispatch-cta">
                  {askingId === d.id ? <Loader2 size={14} className="rs-spin" /> : <span>File →</span>}
                </span>
              </button>
            </li>
          ))}
        </ol>
      </section>

      {/* ── DOSSIER INDEX ── */}
      <section className="rs-dossiers">
        <div className="rs-section-head">
          <div className="rs-section-label">§ The Dossier Index</div>
          <div className="rs-section-rule" aria-hidden />
          <div className="rs-dossier-sort">
            {(['name', 'wins', 'problems'] as const).map(s => (
              <button
                key={s}
                onClick={() => setClientSort(s)}
                className={`rs-sort-btn ${clientSort === s ? 'rs-sort-active' : ''}`}
              >
                {s === 'name' ? 'A–Z' : `By ${s}`}
              </button>
            ))}
          </div>
        </div>

        {loadError && <div className="rs-warning">{loadError}</div>}

        <ul className="rs-dossier-list">
          {sortedClients.map(c => (
            <li key={c.slug}>
              <button onClick={() => openClient(c.slug)} className="rs-dossier-row">
                <span className="rs-dossier-name">{c.client_name}</span>
                <span className="rs-dossier-leader" aria-hidden />
                <span className="rs-dossier-chips">
                  {c.pain_count > 0 && <Chip n={c.pain_count} l="pain" tone="ember" />}
                  {c.tool_count > 0 && <Chip n={c.tool_count} l="switch" tone="ochre" />}
                  {(c.win_count_immediate + c.win_count_long_term) > 0 &&
                    <Chip n={c.win_count_immediate + c.win_count_long_term} l="win" tone="moss" />}
                  {c.problem_count > 0 && <Chip n={c.problem_count} l="friction" tone="rust" />}
                  {c.contrarian_count > 0 && <Chip n={c.contrarian_count} l="contrarian" tone="plum" />}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* ── INFOGRAPHIC: SANKEY ── */}
      <section className="rs-figure">
        <div className="rs-section-head">
          <div className="rs-section-label">¶ Figure I — The Flow</div>
          <div className="rs-section-rule" aria-hidden />
        </div>
        <div className="rs-figure-caption">
          Aggregate journey across every customer. Tools they left,
          on the left. Pains they hit, in the middle. Wins they
          secured with RevSure, on the right. Line weight encodes the
          number of customers on each path.
        </div>
        <div className="rs-figure-frame">
          {sankeyData ? (
            <SankeyFlow nodes={sankeyData.nodes} links={sankeyData.links} height={520} />
          ) : (
            <div className="rs-figure-empty">Figure compiling…</div>
          )}
        </div>
        <div className="rs-figure-source">Source: {clients.length} customer calls · indexed via RevSure transcript pipeline.</div>
      </section>

      {/* ── INFOGRAPHIC: GRAPH ── */}
      <section className="rs-figure">
        <div className="rs-section-head">
          <div className="rs-section-label">¶ Figure II — The Network</div>
          <div className="rs-section-rule" aria-hidden />
        </div>
        <div className="rs-figure-caption">
          The full knowledge graph. Each customer is a hub. Every claim
          orbits its customer, and every claim cites a quote.
          Drag, zoom, click a node to drill in.
        </div>
        <div className="rs-legend">
          {Object.entries({
            Client: PALETTE.Client, Pain: PALETTE.Pain, ToolFrom: PALETTE.ToolFrom,
            Win: PALETTE.Win, Friction: PALETTE.RevSureProblem,
            Contrarian: PALETTE.Contrarian, Tussle: PALETTE.Tussle, Quote: PALETTE.Quote,
          }).map(([k, v]) => (
            <span key={k} className="rs-legend-item">
              <span className="rs-legend-dot" style={{ background: v as string }} />
              {k}
            </span>
          ))}
        </div>
        <div className="rs-figure-frame">
          {graphData ? (
            <ForceGraph
              nodes={graphData.nodes}
              links={graphData.links}
              height={680}
              palette={PALETTE}
            />
          ) : (
            <div className="rs-figure-empty">Graph compiling…</div>
          )}
        </div>
      </section>

      <footer className="rs-footer">
        <div className="rs-rule rs-rule-double" aria-hidden />
        <div className="rs-footer-line">— end of brief —</div>
      </footer>

      {/* ── CLIENT DETAIL DRAWER ── */}
      {selectedClient && (
        <div className="rs-drawer-backdrop" onClick={() => setSelectedClient(null)}>
          <div className="rs-drawer" onClick={(e) => e.stopPropagation()}>
            {!clientDetail ? (
              <div className="rs-drawer-loading">
                <Loader2 size={16} className="rs-spin" />
                Pulling dossier…
              </div>
            ) : (
              <ClientDossier detail={clientDetail} onClose={() => setSelectedClient(null)} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ n, l }: { n: number; l: string }) {
  return (
    <div className="rs-stat">
      <div className="rs-stat-n">{n.toLocaleString()}</div>
      <div className="rs-stat-l">{l}</div>
    </div>
  )
}

function Chip({ n, l, tone }: { n: number; l: string; tone: string }) {
  return <span className={`rs-chip rs-chip-${tone}`}>{n}<span className="rs-chip-l"> {l}</span></span>
}

// ── DOSSIER (drawer) ──
function ClientDossier({ detail, onClose }: { detail: any; onClose: () => void }) {
  const before = detail.before_state || {}
  const after = detail.after_state || {}
  const f = detail.findings || {}
  const wins = f.wins || {}
  return (
    <div className="rs-dossier-detail">
      <div className="rs-drawer-head">
        <div>
          <div className="rs-kicker rs-kicker-accent">Case File</div>
          <h3 className="rs-dossier-h">{detail.client_name}</h3>
          <div className="rs-dossier-sub">
            {detail.call_type} · {(detail._meta?.source_files || []).length} source transcript{(detail._meta?.source_files || []).length === 1 ? '' : 's'}
          </div>
        </div>
        <button onClick={onClose} className="rs-answer-close" aria-label="Close">
          <X size={18} />
        </button>
      </div>

      <div className="rs-rule rs-rule-thin" aria-hidden />

      <div className="rs-beforeafter">
        <article className="rs-ba rs-ba-before">
          <div className="rs-ba-kicker">Before RevSure</div>
          {before.pain_summary && <p className="rs-ba-quote">“{before.pain_summary}”</p>}
          {(before.stack || []).length > 0 && (
            <div className="rs-ba-block">
              <div className="rs-ba-label">Stack</div>
              <div className="rs-ba-tags">
                {before.stack.map((s: string, i: number) => <span key={i} className="rs-tag">{s}</span>)}
              </div>
            </div>
          )}
          {(before.kpis_unhealthy || []).length > 0 && (
            <div className="rs-ba-block">
              <div className="rs-ba-label">Unhealthy KPIs</div>
              <ul className="rs-ba-list">
                {before.kpis_unhealthy.map((k: string, i: number) => <li key={i}>{k}</li>)}
              </ul>
            </div>
          )}
        </article>
        <article className="rs-ba rs-ba-after">
          <div className="rs-ba-kicker">After RevSure</div>
          {after.with_revsure && <p className="rs-ba-quote">“{after.with_revsure}”</p>}
          {(after.wins_realized || []).length > 0 && (
            <div className="rs-ba-block">
              <div className="rs-ba-label">Wins realized</div>
              <ul className="rs-ba-list">
                {after.wins_realized.map((w: string, i: number) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}
          {(after.open_issues || []).length > 0 && (
            <div className="rs-ba-block">
              <div className="rs-ba-label">Open issues</div>
              <ul className="rs-ba-list rs-ba-list-dim">
                {after.open_issues.map((o: string, i: number) => <li key={i}>{o}</li>)}
              </ul>
            </div>
          )}
        </article>
      </div>

      <div className="rs-findings">
        <FindingsBlock title="Pains" items={f.pains || []} tone="ember" labelField="summary" />
        <FindingsBlock title="Tools switched from" items={f.tools_switched_from || []} tone="ochre" labelField="tool" extra={(i: any) => i.vendor ? ` (${i.vendor})` : ''} />
        <FindingsBlock title="Political tussles" items={f.political_tussles || []} tone="plum" labelField="tension_label" extra={(i: any) => (i.actors || []).length ? ` — ${(i.actors || []).join(' ↔ ')}` : ''} />
        <FindingsBlock title="Contrarian claims" items={f.contrarians || []} tone="plum" labelField="claim" />
        <FindingsBlock title="Problems with RevSure" items={f.revsure_problems || []} tone="rust" labelField="problem" extra={(i: any) => i.category ? ` [${i.category}]` : ''} />
        <FindingsBlock title="Wins — immediate" items={wins.immediate || []} tone="moss" labelField="win" />
        <FindingsBlock title="Wins — long term" items={wins.long_term || []} tone="moss" labelField="win" />
        <FindingsBlock title="Best about RevSure" items={f.best_about_revsure || []} tone="moss" labelField="summary" />
      </div>
    </div>
  )
}

function FindingsBlock({
  title, items, tone, labelField, extra,
}: { title: string; items: any[]; tone: string; labelField: string; extra?: (i: any) => string }) {
  if (!items.length) return null
  return (
    <section className={`rs-findings-block rs-tone-${tone}`}>
      <h4 className="rs-findings-h">
        <span className="rs-findings-title">{title}</span>
        <span className="rs-findings-count">{items.length}</span>
      </h4>
      <ul className="rs-findings-items">
        {items.map((it, i) => (
          <li key={i}>
            <div className="rs-findings-claim">{it[labelField]}{extra ? extra(it) : ''}</div>
            {it.quote && (
              <p className="rs-findings-quote">
                “{it.quote}”
                <span className="rs-findings-attr"> — {it.speaker || 'unknown'} <span className="rs-mono-small rs-dim">@ {it.timestamp || '?'}</span></span>
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

// ── Scoped styles ──
function ScopedStyles() {
  return (
    <style>{`
      .revsure-root {
        --paper:        #0e0b08;
        --paper-soft:   #15110d;
        --ink:          #f3eadb;
        --ink-soft:     rgba(243, 234, 219, 0.74);
        --ink-mute:     rgba(243, 234, 219, 0.48);
        --ink-faint:    rgba(243, 234, 219, 0.22);
        --rule:         rgba(243, 234, 219, 0.18);
        --rule-strong:  rgba(243, 234, 219, 0.42);
        --ember:        #e85d3c;
        --ember-soft:   rgba(232, 93, 60, 0.16);
        --ochre:        #c89455;
        --ochre-soft:   rgba(200, 148, 85, 0.16);
        --moss:         #8aa67a;
        --moss-soft:    rgba(138, 166, 122, 0.16);
        --rust:         #d97a3a;
        --rust-soft:    rgba(217, 122, 58, 0.16);
        --plum:         #b06c8a;
        --plum-soft:    rgba(176, 108, 138, 0.18);

        --display: "Fraunces", "Iowan Old Style", "Source Serif Pro", Georgia, serif;
        --body:    "DM Sans", system-ui, sans-serif;
        --mono:    "JetBrains Mono", ui-monospace, monospace;

        position: relative;
        min-height: 100vh;
        background: var(--paper);
        color: var(--ink);
        font-family: var(--body);
        -webkit-font-smoothing: antialiased;
        text-rendering: geometricPrecision;
        font-feature-settings: "kern", "liga", "calt";
        overflow-x: hidden;
      }

      /* Subtle warm-paper grain */
      .revsure-root::before {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 0;
        opacity: 0.55;
        background:
          radial-gradient(1200px 800px at 20% -10%, rgba(232, 93, 60, 0.06), transparent 60%),
          radial-gradient(900px 600px at 110% 30%, rgba(200, 148, 85, 0.04), transparent 65%),
          repeating-linear-gradient(0deg, rgba(255,255,255,0.012) 0 1px, transparent 1px 3px);
      }

      .revsure-root > * { position: relative; z-index: 1; }

      /* ── Rules ── */
      .rs-rule { height: 0; border: 0; }
      .rs-rule-top      { border-top: 1px solid var(--rule); }
      .rs-rule-thin     { border-top: 1px solid var(--rule); margin: 18px 0; }
      .rs-rule-double   { border-top: 1px solid var(--rule-strong); box-shadow: 0 3px 0 -2px var(--rule); padding-bottom: 3px; margin: 12px 0; }
      .rs-mt-32         { margin-top: 32px !important; }

      /* ── Masthead ── */
      .rs-masthead {
        max-width: 1100px;
        margin: 0 auto;
        padding: 56px 32px 28px;
      }
      .rs-masthead-row {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        font-family: var(--mono);
        font-size: 11px;
        letter-spacing: 0.14em;
        color: var(--ink-mute);
        padding: 14px 0 12px;
        flex-wrap: wrap;
        gap: 12px;
      }
      .rs-tagline {
        font-family: var(--display);
        font-style: italic;
        font-size: 14px;
        letter-spacing: 0.02em;
        color: var(--ink-soft);
        text-transform: none;
      }
      .rs-title {
        text-align: center;
        margin: 18px 0 4px;
        line-height: 0.92;
        font-family: var(--display);
        font-weight: 500;
        font-size: clamp(72px, 13vw, 168px);
        letter-spacing: -0.04em;
        font-feature-settings: "ss01", "kern", "liga";
      }
      .rs-title-ask {
        font-style: italic;
        font-weight: 400;
        color: var(--ember);
        padding-right: 0.06em;
      }
      .rs-title-rev {
        font-weight: 500;
        color: var(--ink);
      }
      .rs-standfirst {
        max-width: 640px;
        margin: 26px auto 30px;
        text-align: center;
        font-family: var(--display);
        font-size: 19px;
        line-height: 1.55;
        color: var(--ink-soft);
        font-weight: 400;
        letter-spacing: 0.005em;
      }
      .rs-standfirst em {
        font-style: italic;
        color: var(--ember);
        font-weight: 500;
      }
      .rs-search {
        display: flex;
        align-items: stretch;
        max-width: 720px;
        margin: 0 auto;
        border-top: 1px solid var(--rule-strong);
        border-bottom: 1px solid var(--rule-strong);
        background: transparent;
        padding: 6px 0;
      }
      .rs-search-prompt {
        font-family: var(--display);
        font-style: italic;
        font-size: 28px;
        color: var(--ember);
        padding: 10px 16px 10px 4px;
        align-self: center;
        letter-spacing: -0.01em;
      }
      .rs-search-input {
        flex: 1;
        background: transparent;
        border: 0;
        outline: 0;
        color: var(--ink);
        font-family: var(--display);
        font-size: 22px;
        padding: 14px 8px;
        letter-spacing: -0.005em;
      }
      .rs-search-input::placeholder {
        color: var(--ink-mute);
        font-style: italic;
      }
      .rs-search-btn {
        background: transparent;
        border: 0;
        color: var(--ember);
        font-family: var(--display);
        font-size: 28px;
        cursor: pointer;
        padding: 0 16px;
        align-self: center;
      }
      .rs-search-btn:disabled { opacity: 0.35; cursor: not-allowed; }
      .rs-spin { animation: rs-spin 1s linear infinite; }
      @keyframes rs-spin { to { transform: rotate(360deg); } }

      /* ── Kicker labels ── */
      .rs-kicker {
        font-family: var(--mono);
        font-size: 11px;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        color: var(--ink-mute);
      }
      .rs-kicker-accent { color: var(--ember); }

      /* ── By the numbers ── */
      .rs-numbers {
        max-width: 1100px;
        margin: 60px auto 24px;
        padding: 0 32px;
      }
      .rs-numbers-grid {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 0;
        margin-top: 14px;
        border-top: 1px solid var(--rule);
        border-bottom: 1px solid var(--rule);
      }
      .rs-stat {
        padding: 22px 16px;
        border-right: 1px solid var(--rule);
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .rs-stat:last-child { border-right: 0; }
      .rs-stat-n {
        font-family: var(--display);
        font-size: 38px;
        font-weight: 500;
        letter-spacing: -0.02em;
        color: var(--ink);
        font-variant-numeric: lining-nums tabular-nums;
      }
      .rs-stat-l {
        font-family: var(--mono);
        font-size: 10px;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--ink-mute);
      }
      @media (max-width: 900px) {
        .rs-numbers-grid { grid-template-columns: repeat(3, 1fr); }
        .rs-stat:nth-child(3) { border-right: 0; }
      }
      @media (max-width: 540px) {
        .rs-numbers-grid { grid-template-columns: repeat(2, 1fr); }
        .rs-stat { border-right: 1px solid var(--rule); }
        .rs-stat:nth-child(even) { border-right: 0; }
      }

      /* ── Section heads ── */
      .rs-section-head {
        display: flex;
        align-items: center;
        gap: 18px;
        margin: 0 0 22px;
      }
      .rs-section-label {
        font-family: var(--display);
        font-style: italic;
        font-size: 22px;
        color: var(--ember);
        white-space: nowrap;
        letter-spacing: -0.005em;
      }
      .rs-section-rule {
        flex: 1;
        border-top: 1px solid var(--rule);
      }
      .rs-section-meta {
        font-family: var(--mono);
        font-size: 10px;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--ink-mute);
      }

      /* ── Dispatches ── */
      .rs-dispatches {
        max-width: 1100px;
        margin: 64px auto 0;
        padding: 0 32px;
      }
      .rs-dispatch-list {
        list-style: none;
        padding: 0;
        margin: 0;
        border-top: 1px solid var(--rule);
      }
      .rs-dispatch {
        border-bottom: 1px solid var(--rule);
      }
      .rs-dispatch-btn {
        display: grid;
        grid-template-columns: 80px 1fr auto;
        gap: 28px;
        align-items: start;
        width: 100%;
        background: transparent;
        border: 0;
        text-align: left;
        cursor: pointer;
        padding: 30px 10px;
        color: var(--ink);
        transition: background 200ms ease, padding 200ms ease;
      }
      .rs-dispatch-btn:hover {
        background: linear-gradient(90deg, var(--ember-soft), transparent 70%);
        padding-left: 22px;
      }
      .rs-dispatch-btn:disabled { opacity: 0.5; cursor: not-allowed; }
      .rs-dispatch-num {
        font-family: var(--display);
        font-style: italic;
        font-size: 56px;
        line-height: 0.85;
        color: var(--ember);
        font-weight: 500;
        font-variant-numeric: oldstyle-nums;
      }
      .rs-dispatch-body { min-width: 0; }
      .rs-dispatch-kicker {
        font-family: var(--mono);
        font-size: 10px;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        color: var(--ink-mute);
        margin-bottom: 6px;
      }
      .rs-dispatch-head {
        font-family: var(--display);
        font-size: 26px;
        font-weight: 500;
        line-height: 1.18;
        letter-spacing: -0.015em;
        color: var(--ink);
        margin-bottom: 6px;
      }
      .rs-dispatch-deck {
        font-family: var(--body);
        font-size: 14px;
        line-height: 1.6;
        color: var(--ink-soft);
        max-width: 60ch;
      }
      .rs-dispatch-cta {
        align-self: center;
        font-family: var(--mono);
        font-size: 11px;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--ember);
        padding-right: 4px;
        white-space: nowrap;
      }
      @media (max-width: 720px) {
        .rs-dispatch-btn { grid-template-columns: 48px 1fr; gap: 18px; padding: 22px 6px; }
        .rs-dispatch-cta { grid-column: 2; padding-top: 6px; }
        .rs-dispatch-num { font-size: 38px; }
        .rs-dispatch-head { font-size: 21px; }
      }

      /* ── Dossier index ── */
      .rs-dossiers {
        max-width: 1100px;
        margin: 88px auto 0;
        padding: 0 32px;
      }
      .rs-dossier-sort {
        display: flex;
        gap: 4px;
      }
      .rs-sort-btn {
        font-family: var(--mono);
        font-size: 10px;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        background: transparent;
        color: var(--ink-mute);
        border: 1px solid var(--rule);
        padding: 6px 10px;
        cursor: pointer;
        transition: color 200ms, border-color 200ms;
      }
      .rs-sort-btn:hover { color: var(--ink); }
      .rs-sort-active { color: var(--ember); border-color: var(--ember); }
      .rs-warning {
        font-family: var(--body);
        font-size: 13px;
        color: var(--ochre);
        background: var(--ochre-soft);
        border-left: 3px solid var(--ochre);
        padding: 12px 16px;
        margin-bottom: 18px;
      }
      .rs-dossier-list {
        list-style: none;
        padding: 0;
        margin: 0;
        border-top: 1px solid var(--rule);
      }
      .rs-dossier-row {
        display: flex;
        align-items: baseline;
        gap: 14px;
        width: 100%;
        padding: 16px 8px;
        background: transparent;
        border: 0;
        border-bottom: 1px solid var(--rule);
        cursor: pointer;
        color: var(--ink);
        text-align: left;
        transition: padding 180ms, background 180ms;
      }
      .rs-dossier-row:hover {
        background: linear-gradient(90deg, var(--ember-soft), transparent 60%);
        padding-left: 18px;
      }
      .rs-dossier-name {
        font-family: var(--display);
        font-size: 22px;
        font-weight: 500;
        letter-spacing: -0.01em;
        white-space: nowrap;
      }
      .rs-dossier-leader {
        flex: 1;
        border-bottom: 1px dotted var(--ink-faint);
        align-self: center;
        height: 1px;
        margin: 0 4px;
        min-width: 24px;
      }
      .rs-dossier-chips {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        justify-content: flex-end;
      }

      /* ── Chips ── */
      .rs-chip {
        font-family: var(--mono);
        font-size: 11px;
        letter-spacing: 0.06em;
        padding: 3px 8px;
        border: 1px solid currentColor;
        border-radius: 1px;
        white-space: nowrap;
        line-height: 1.1;
      }
      .rs-chip-l {
        font-size: 9px;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        opacity: 0.72;
        margin-left: 4px;
      }
      .rs-chip-ember { color: var(--ember); background: var(--ember-soft); }
      .rs-chip-ochre { color: var(--ochre); background: var(--ochre-soft); }
      .rs-chip-moss  { color: var(--moss);  background: var(--moss-soft); }
      .rs-chip-rust  { color: var(--rust);  background: var(--rust-soft); }
      .rs-chip-plum  { color: var(--plum);  background: var(--plum-soft); }

      /* ── Figures (sankey + graph) ── */
      .rs-figure {
        max-width: 1100px;
        margin: 88px auto 0;
        padding: 0 32px;
      }
      .rs-figure-caption {
        font-family: var(--display);
        font-style: italic;
        font-size: 16px;
        line-height: 1.55;
        color: var(--ink-soft);
        max-width: 70ch;
        margin: 0 0 18px;
      }
      .rs-figure-frame {
        border: 1px solid var(--rule);
        background: var(--paper-soft);
        padding: 14px;
        position: relative;
      }
      .rs-figure-frame::before,
      .rs-figure-frame::after {
        content: "";
        position: absolute;
        width: 14px;
        height: 14px;
        border: 1px solid var(--ember);
      }
      .rs-figure-frame::before {
        top: -1px; left: -1px;
        border-right: 0;
        border-bottom: 0;
      }
      .rs-figure-frame::after {
        bottom: -1px; right: -1px;
        border-left: 0;
        border-top: 0;
      }
      .rs-figure-empty {
        display: flex;
        align-items: center;
        justify-content: center;
        height: 480px;
        font-family: var(--display);
        font-style: italic;
        color: var(--ink-mute);
      }
      .rs-figure-source {
        font-family: var(--mono);
        font-size: 10px;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--ink-mute);
        margin-top: 10px;
      }
      .rs-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 14px;
        margin: 0 0 14px;
      }
      .rs-legend-item {
        font-family: var(--mono);
        font-size: 10px;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: var(--ink-soft);
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }
      .rs-legend-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        display: inline-block;
      }

      /* ── Answer card ── */
      .rs-answer {
        position: relative;
        max-width: 920px;
        margin: 48px auto 24px;
        padding: 28px 32px 32px;
        background: var(--paper-soft);
        border-top: 1px solid var(--ember);
        border-bottom: 1px solid var(--ember);
      }
      .rs-answer-close {
        position: absolute;
        top: 14px; right: 14px;
        background: transparent;
        border: 0;
        color: var(--ink-mute);
        cursor: pointer;
        padding: 4px;
      }
      .rs-answer-close:hover { color: var(--ink); }
      .rs-answer-body {
        font-family: var(--display);
        font-size: 20px;
        line-height: 1.6;
        color: var(--ink);
        white-space: pre-wrap;
        margin: 18px 0 0;
        letter-spacing: -0.005em;
      }
      .rs-citations-head {
        font-family: var(--mono);
        font-size: 10px;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        color: var(--ember);
        margin: 6px 0 14px;
      }
      .rs-mono-small {
        font-family: var(--mono);
        font-size: 11px;
        letter-spacing: 0.04em;
      }
      .rs-dim { color: var(--ink-mute); }
      .rs-citations {
        list-style: none;
        padding: 0;
        margin: 0;
        display: flex;
        flex-direction: column;
        gap: 18px;
      }
      .rs-citation {
        display: grid;
        grid-template-columns: 38px 1fr;
        gap: 16px;
        align-items: start;
      }
      .rs-citation-num {
        font-family: var(--display);
        font-style: italic;
        font-size: 26px;
        color: var(--ember);
        line-height: 1;
        padding-top: 4px;
      }
      .rs-citation-meta {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        gap: 6px;
        font-size: 12px;
        color: var(--ink-mute);
        margin-bottom: 8px;
      }
      .rs-citation-client {
        font-family: var(--display);
        font-style: italic;
        font-size: 15px;
        color: var(--ink);
        font-weight: 500;
      }
      .rs-citation-cat {
        font-family: var(--mono);
        font-size: 10px;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        color: var(--ember);
      }
      .rs-dot { color: var(--ink-faint); }
      .rs-citation-quote {
        margin: 0;
        font-family: var(--display);
        font-style: italic;
        font-size: 16px;
        line-height: 1.55;
        color: var(--ink-soft);
        border-left: 2px solid var(--ember);
        padding-left: 12px;
      }

      /* ── Drawer (case file) ── */
      .rs-drawer-backdrop {
        position: fixed;
        inset: 0;
        z-index: 50;
        background: rgba(5, 4, 3, 0.78);
        display: flex;
        align-items: flex-end;
        justify-content: center;
        backdrop-filter: blur(4px);
      }
      .rs-drawer {
        width: 100%;
        max-width: 920px;
        max-height: 90vh;
        overflow-y: auto;
        background: var(--paper);
        border-top: 1px solid var(--ember);
        padding: 32px 36px 48px;
      }
      @media (min-width: 720px) {
        .rs-drawer-backdrop { align-items: center; }
        .rs-drawer { border: 1px solid var(--ember); }
      }
      .rs-drawer-loading {
        display: flex;
        align-items: center;
        gap: 10px;
        color: var(--ink-mute);
        font-family: var(--mono);
        font-size: 12px;
        letter-spacing: 0.16em;
        text-transform: uppercase;
      }
      .rs-drawer-head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 20px;
        margin-bottom: 6px;
      }
      .rs-dossier-h {
        font-family: var(--display);
        font-size: 44px;
        font-weight: 500;
        letter-spacing: -0.025em;
        line-height: 1;
        margin: 6px 0 6px;
      }
      .rs-dossier-sub {
        font-family: var(--mono);
        font-size: 10px;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: var(--ink-mute);
      }

      .rs-beforeafter {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 18px;
        margin: 24px 0 32px;
      }
      @media (max-width: 720px) { .rs-beforeafter { grid-template-columns: 1fr; } }
      .rs-ba {
        background: var(--paper-soft);
        border: 1px solid var(--rule);
        padding: 20px;
        position: relative;
      }
      .rs-ba-before { border-left: 3px solid var(--ochre); }
      .rs-ba-after  { border-left: 3px solid var(--moss); }
      .rs-ba-kicker {
        font-family: var(--mono);
        font-size: 10px;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        color: var(--ink-mute);
        margin-bottom: 12px;
      }
      .rs-ba-before .rs-ba-kicker { color: var(--ochre); }
      .rs-ba-after  .rs-ba-kicker { color: var(--moss); }
      .rs-ba-quote {
        font-family: var(--display);
        font-style: italic;
        font-size: 17px;
        line-height: 1.55;
        color: var(--ink);
        margin: 0 0 14px;
      }
      .rs-ba-block { margin-top: 12px; }
      .rs-ba-label {
        font-family: var(--mono);
        font-size: 9px;
        letter-spacing: 0.2em;
        text-transform: uppercase;
        color: var(--ink-mute);
        margin-bottom: 6px;
      }
      .rs-ba-tags { display: flex; flex-wrap: wrap; gap: 6px; }
      .rs-tag {
        font-family: var(--mono);
        font-size: 11px;
        background: var(--paper);
        border: 1px solid var(--rule);
        padding: 3px 7px;
        color: var(--ink-soft);
      }
      .rs-ba-list {
        list-style: none;
        padding: 0; margin: 0;
        font-family: var(--body);
        font-size: 13px;
        line-height: 1.6;
      }
      .rs-ba-list li {
        padding-left: 14px;
        position: relative;
      }
      .rs-ba-list li::before {
        content: "—";
        position: absolute;
        left: 0;
        color: var(--ink-faint);
      }
      .rs-ba-list-dim { color: var(--ink-mute); }

      .rs-findings { display: flex; flex-direction: column; gap: 18px; }
      .rs-findings-block {
        border: 1px solid var(--rule);
        padding: 16px 18px;
        background: var(--paper-soft);
        border-left-width: 3px;
      }
      .rs-tone-ember { border-left-color: var(--ember); }
      .rs-tone-ochre { border-left-color: var(--ochre); }
      .rs-tone-moss  { border-left-color: var(--moss); }
      .rs-tone-rust  { border-left-color: var(--rust); }
      .rs-tone-plum  { border-left-color: var(--plum); }
      .rs-findings-h {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        margin: 0 0 10px;
      }
      .rs-findings-title {
        font-family: var(--display);
        font-style: italic;
        font-size: 18px;
        color: var(--ink);
      }
      .rs-findings-count {
        font-family: var(--mono);
        font-size: 10px;
        letter-spacing: 0.18em;
        color: var(--ink-mute);
      }
      .rs-findings-items {
        list-style: none;
        padding: 0; margin: 0;
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .rs-findings-claim {
        font-family: var(--body);
        font-size: 14px;
        font-weight: 500;
        color: var(--ink);
      }
      .rs-findings-quote {
        font-family: var(--display);
        font-style: italic;
        font-size: 13px;
        line-height: 1.55;
        color: var(--ink-soft);
        margin: 4px 0 0;
      }
      .rs-findings-attr {
        font-family: var(--body);
        font-style: normal;
        font-size: 11px;
        color: var(--ink-mute);
      }

      /* ── Footer ── */
      .rs-footer {
        max-width: 1100px;
        margin: 88px auto 0;
        padding: 0 32px 56px;
      }
      .rs-footer-line {
        text-align: center;
        font-family: var(--display);
        font-style: italic;
        color: var(--ember);
        margin-top: 12px;
        font-size: 14px;
        letter-spacing: 0.04em;
      }
    `}</style>
  )
}
