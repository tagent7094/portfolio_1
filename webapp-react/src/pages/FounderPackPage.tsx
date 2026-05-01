import { useEffect, useState, useCallback, useMemo } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft, FileSpreadsheet, Calendar, ChevronDown, ChevronRight,
  Loader2, X, BookOpen, Lightbulb, Quote, CheckCircle2,
} from 'lucide-react'
import clsx from 'clsx'
import { apiGet } from '../api/client'

// ── Types ────────────────────────────────────────────────────────────────────

interface Pack { filename: string; date: string; size_kb: number }

interface PackData {
  readme: Record<string, string>
  headers: string[]
  posts: Record<string, any>[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function truncate(text: any, max = 130): string {
  const s = String(text ?? '')
  return s.length > max ? s.slice(0, max) + '…' : s
}

/** Find the first header that starts with a given prefix */
function findCol(headers: string[], prefix: string): string {
  return headers.find((h) => h.startsWith(prefix)) ?? prefix
}

/** All "Status (*)" columns in order */
function statusCols(headers: string[]): string[] {
  return headers.filter((h) => h.startsWith('Status'))
}

// Variant letters present in this sheet
const VARIANT_LETTERS = ['A', 'B', 'C', 'D', 'E'] as const

/** Build variant data from a post row given the actual column names */
function getVariants(post: Record<string, any>, headers: string[]) {
  return VARIANT_LETTERS.map((v) => {
    const opening = post[`${v}, Opening`] ?? post[`${v} - Opening`] ?? ''
    const type    = post[`${v}, Rewrite Type`] ?? post[`${v} - Rewrite Type`] ?? ''
    const change  = post[`${v}, Key Change`] ?? post[`${v} - Key Change`] ?? ''
    const lift    = post[`${v}, Expected Lift`] ?? post[`${v} - Expected Lift`] ?? ''
    return { letter: v, opening: String(opening), type: String(type), change: String(change), lift: Number(lift) || 0 }
  }).filter((v) => v.opening)
}

// ── Small components ─────────────────────────────────────────────────────────

function RecBadge({ v, size = 'md' }: { v: string; size?: 'sm' | 'md' }) {
  if (!v) return <span className="text-white/20 text-xs">—</span>
  return (
    <span className={clsx(
      'inline-flex items-center justify-center rounded-full font-bold bg-white text-black',
      size === 'sm' ? 'h-5 w-5 text-[10px]' : 'h-6 w-6 text-xs',
    )}>
      {v}
    </span>
  )
}

function TypeBadge({ type }: { type: string }) {
  const isBatch = type?.startsWith('B')
  return (
    <span className={clsx(
      'inline-flex h-6 min-w-[2rem] items-center justify-center rounded font-mono text-[11px] font-semibold px-1.5',
      isBatch ? 'bg-white/[0.06] text-white/50' : 'bg-white/[0.1] text-white/70',
    )}>
      {type}
    </span>
  )
}

function LiftDots({ score }: { score: number }) {
  return (
    <span className="inline-flex gap-0.5 items-center">
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={clsx('h-1.5 w-1.5 rounded-full', i <= score ? 'bg-white/70' : 'bg-white/10')} />
      ))}
    </span>
  )
}

function StatusPill({ value }: { value: string }) {
  if (!value) return null
  return (
    <span className="rounded px-1.5 py-0.5 text-[10px] bg-white/[0.05] text-white/40 border border-white/[0.07]">
      {value}
    </span>
  )
}

// ── Detail panel ─────────────────────────────────────────────────────────────

function DetailPanel({
  post,
  headers,
  onClose,
}: {
  post: Record<string, any>
  headers: string[]
  onClose: () => void
}) {
  const rec      = String(post['Recommended'] ?? '')
  const variants = getVariants(post, headers)
  const statCols = statusCols(headers)
  const finalPost = post['Finalized Post'] || post['Final Post'] || ''
  const whyText   = post['Why'] ?? ''
  const sourceQ   = post['Source Quote'] ?? ''
  const mechanic  = post['Mechanic'] ?? ''
  const buried    = post["Buried Gold (from this post's paras 2-4)"] ?? ''
  const weakness  = post['Weakness'] ?? ''
  const topic     = post['Post Topic (derived from body)'] ?? ''
  const domain    = post['Domain'] ?? ''

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-end bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative flex h-screen w-full max-w-2xl flex-col bg-[#0a0a0a] border-l border-white/10 animate-slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 px-6 py-4">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="font-mono text-xs text-white/30">#{post['Row #']}</span>
            <TypeBadge type={String(post['Type'] ?? '')} />
            {rec && (
              <span className="flex items-center gap-1 rounded-full bg-white px-2.5 py-0.5 text-[11px] font-bold text-black">
                <CheckCircle2 size={10} /> Rec: {rec}
              </span>
            )}
            {statCols.map((col) => post[col] ? (
              <StatusPill key={col} value={String(post[col])} />
            ) : null)}
          </div>
          <button onClick={onClose} className="shrink-0 text-white/30 hover:text-white transition-colors">
            <X size={18} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto">
          <div className="space-y-5 p-6">

            {/* Final / Finalized post */}
            <section>
              <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-white/30">
                <BookOpen size={11} />
                {finalPost !== post['Final Post'] && finalPost ? 'Finalized post (rewritten opening)' : 'Final post'}
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-white/90 leading-[1.75] whitespace-pre-wrap">
                {finalPost || '—'}
              </div>
            </section>

            {/* Why */}
            {whyText && (
              <section>
                <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-white/30">
                  <Lightbulb size={11} /> Why this variant wins
                </div>
                <p className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm text-white/65 leading-relaxed">
                  {whyText}
                </p>
              </section>
            )}

            {/* Opening variants */}
            {variants.length > 0 && (
              <section>
                <div className="mb-3 text-[10px] font-semibold uppercase tracking-widest text-white/30">
                  Opening variants
                </div>
                <div className="space-y-2">
                  {variants.map(({ letter, opening, type, change, lift }) => {
                    const isRec = rec === letter
                    return (
                      <div key={letter} className={clsx(
                        'rounded-xl border p-3.5',
                        isRec ? 'border-white/25 bg-white/[0.05]' : 'border-white/[0.07] bg-white/[0.02]',
                      )}>
                        <div className="mb-2 flex items-start gap-2">
                          <span className={clsx(
                            'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold',
                            isRec ? 'bg-white text-black' : 'bg-white/10 text-white/50',
                          )}>
                            {letter}
                          </span>
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 flex-1 min-w-0">
                            {type && <span className="text-[10px] text-white/35 shrink-0">{type}</span>}
                            {lift > 0 && <LiftDots score={lift} />}
                          </div>
                        </div>
                        <p className={clsx('text-sm leading-snug pl-7', isRec ? 'text-white/85' : 'text-white/65')}>
                          {opening}
                        </p>
                        {change && (
                          <p className="mt-1.5 pl-7 text-[11px] text-white/30 italic">{change}</p>
                        )}
                      </div>
                    )
                  })}
                </div>
              </section>
            )}

            {/* Source */}
            {sourceQ && (
              <section>
                <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-white/30">
                  <Quote size={11} /> Source
                </div>
                <blockquote className="rounded-xl border-l-2 border-white/15 bg-white/[0.02] py-3 pl-4 pr-4 text-xs text-white/45 leading-relaxed italic">
                  {sourceQ}
                </blockquote>
                {mechanic && (
                  <p className="mt-2 text-[10px] text-white/25">Mechanic: {mechanic}</p>
                )}
              </section>
            )}

            {/* Meta grid */}
            <section className="grid grid-cols-2 gap-2 text-xs">
              {topic && (
                <div className="rounded-lg border border-white/[0.07] bg-white/[0.02] p-3">
                  <div className="mb-1 text-[9px] uppercase tracking-widest text-white/25">Topic</div>
                  <div className="text-white/65 leading-snug">{topic}</div>
                </div>
              )}
              {domain && (
                <div className="rounded-lg border border-white/[0.07] bg-white/[0.02] p-3">
                  <div className="mb-1 text-[9px] uppercase tracking-widest text-white/25">Domain</div>
                  <div className="text-white/65">{domain}</div>
                </div>
              )}
              {buried && (
                <div className="col-span-2 rounded-lg border border-white/[0.07] bg-white/[0.02] p-3">
                  <div className="mb-1 text-[9px] uppercase tracking-widest text-white/25">Buried gold</div>
                  <div className="text-white/55 italic leading-snug">{buried}</div>
                </div>
              )}
              {weakness && (
                <div className="col-span-2 rounded-lg border border-white/[0.07] bg-white/[0.02] p-3">
                  <div className="mb-1 text-[9px] uppercase tracking-widest text-white/25">Weakness</div>
                  <div className="text-white/45 leading-snug">{weakness}</div>
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Source group row ──────────────────────────────────────────────────────────

function SourceGroup({
  sourceNum,
  posts,
  headers,
  defaultOpen,
  onSelectPost,
}: {
  sourceNum: number
  posts: Record<string, any>[]
  headers: string[]
  defaultOpen: boolean
  onSelectPost: (p: Record<string, any>) => void
}) {
  const [open, setOpen] = useState(defaultOpen)
  const firstPost = posts[0]
  const sourceQ = String(firstPost?.['Source Quote'] ?? '')
  const statCols = statusCols(headers)

  return (
    <div className="rounded-2xl border border-white/[0.08] overflow-hidden">
      {/* Source header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-4 px-5 py-4 bg-white/[0.02] hover:bg-white/[0.04] transition-colors text-left"
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-white/15 font-mono text-xs text-white/50">
          {sourceNum}
        </span>
        <span className="flex-1 text-sm text-white/60 line-clamp-1 min-w-0">
          {truncate(sourceQ, 110)}
        </span>
        <span className="shrink-0 text-xs text-white/25">{posts.length} posts</span>
        {open
          ? <ChevronDown size={14} className="shrink-0 text-white/30" />
          : <ChevronRight size={14} className="shrink-0 text-white/30" />}
      </button>

      {/* Post rows */}
      {open && (
        <div className="divide-y divide-white/[0.05]">
          {posts.map((post, idx) => {
            const rec = String(post['Recommended'] ?? '')
            const type = String(post['Type'] ?? '')
            const finalPost = post['Finalized Post'] || post['Final Post'] || ''
            const variants = getVariants(post, headers)
            return (
              <div
                key={idx}
                onClick={() => onSelectPost(post)}
                className="px-5 py-4 hover:bg-white/[0.03] cursor-pointer transition-colors"
              >
                {/* Top row: type + rec + status */}
                <div className="flex items-center gap-2 mb-2.5 flex-wrap">
                  <span className="font-mono text-[10px] text-white/20">#{post['Row #']}</span>
                  <TypeBadge type={type} />
                  <RecBadge v={rec} size="sm" />
                  {statCols.map((col) => post[col] ? (
                    <StatusPill key={col} value={String(post[col])} />
                  ) : null)}
                </div>

                {/* Final post preview */}
                <p className="text-sm text-white/60 leading-snug line-clamp-2 mb-3">
                  {truncate(finalPost, 200)}
                </p>

                {/* Variant openings */}
                {variants.length > 0 && (
                  <div className="space-y-1.5">
                    {variants.map(({ letter, opening, type: vtype, lift }) => {
                      const isRec = rec === letter
                      return (
                        <div key={letter} className={clsx(
                          'flex items-start gap-2 rounded-lg px-2.5 py-1.5',
                          isRec ? 'bg-white/[0.07]' : 'bg-white/[0.02]',
                        )}>
                          <span className={clsx(
                            'flex h-4.5 w-4.5 shrink-0 mt-0.5 items-center justify-center rounded-full text-[9px] font-bold',
                            isRec ? 'bg-white text-black' : 'bg-white/10 text-white/40',
                          )}>
                            {letter}
                          </span>
                          <p className={clsx(
                            'flex-1 text-xs leading-snug line-clamp-2',
                            isRec ? 'text-white/80' : 'text-white/45',
                          )}>
                            {opening}
                          </p>
                          <div className="shrink-0 flex items-center gap-1.5 pt-0.5">
                            {vtype && <span className="text-[9px] text-white/20 hidden sm:block">{vtype}</span>}
                            {lift > 0 && <LiftDots score={lift} />}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function FounderPackPage() {
  const { slug } = useParams<{ slug: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const [authed, setAuthed] = useState<boolean | null>(null)
  const [packs, setPacks] = useState<Pack[]>([])
  const [selectedDate, setSelectedDate] = useState<string>(searchParams.get('date') ?? '')
  const [packData, setPackData] = useState<PackData | null>(null)
  const [loadingPacks, setLoadingPacks] = useState(true)
  const [loadingData, setLoadingData] = useState(false)
  const [selectedPost, setSelectedPost] = useState<Record<string, any> | null>(null)

  // Admin auth
  useEffect(() => {
    apiGet('/api/admin/me')
      .then(() => setAuthed(true))
      .catch(() => { setAuthed(false); navigate('/admin/login', { replace: true }) })
  }, [navigate])

  // Load packs list
  useEffect(() => {
    if (!authed || !slug) return
    setLoadingPacks(true)
    apiGet<{ packs: Pack[] }>(`/api/admin/founders/${slug}/post-packs`)
      .then((d) => {
        setPacks(d.packs)
        if (!selectedDate && d.packs.length > 0) setSelectedDate(d.packs[0].date)
      })
      .catch(() => {})
      .finally(() => setLoadingPacks(false))
  }, [authed, slug])

  // Load pack data
  const loadPackData = useCallback(async (date: string) => {
    if (!slug || !date) return
    setLoadingData(true)
    setPackData(null)
    try {
      setPackData(await apiGet<PackData>(`/api/admin/founders/${slug}/post-packs/${date}`))
    } catch { setPackData(null) }
    finally { setLoadingData(false) }
  }, [slug])

  useEffect(() => {
    if (authed && selectedDate) {
      setSearchParams({ date: selectedDate }, { replace: true })
      loadPackData(selectedDate)
    }
  }, [authed, selectedDate, loadPackData])

  // Group posts by Source #
  const grouped = useMemo(() => {
    if (!packData) return []
    const map = new Map<number, Record<string, any>[]>()
    for (const post of packData.posts) {
      const n = Number(post['Source #']) || 0
      if (!map.has(n)) map.set(n, [])
      map.get(n)!.push(post)
    }
    return Array.from(map.entries()).sort(([a], [b]) => a - b)
  }, [packData])

  const displayName = slug?.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) ?? ''

  if (authed === null) {
    return (
      <div className="flex h-screen items-center justify-center bg-black">
        <Loader2 size={20} className="animate-spin text-white" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-black text-white">

      {/* ── Header ── */}
      <div className="sticky top-0 z-20 border-b border-white/[0.08] bg-black/95 backdrop-blur">
        <div className="mx-auto max-w-4xl px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/admin')}
              className="flex items-center gap-1.5 text-sm text-white/40 hover:text-white transition-colors"
            >
              <ArrowLeft size={14} /> Admin
            </button>
            <span className="text-white/15">/</span>
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/10 text-xs font-semibold">
                {displayName.charAt(0)}
              </div>
              <span className="font-[var(--font-display)] font-semibold text-sm">{displayName}</span>
            </div>
          </div>

          {/* Date selector */}
          <div className="flex items-center gap-2">
            <Calendar size={13} className="text-white/30" />
            {loadingPacks ? (
              <Loader2 size={13} className="animate-spin text-white/30" />
            ) : packs.length === 0 ? (
              <span className="text-xs text-white/25">No packs yet</span>
            ) : (
              <div className="relative">
                <select
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="appearance-none rounded-lg border border-white/10 bg-white/[0.04] pl-3 pr-7 py-1.5 text-xs text-white focus:outline-none focus:border-white/25 cursor-pointer"
                >
                  {packs.map((p) => (
                    <option key={p.date} value={p.date} className="bg-black">
                      {p.date} — {p.filename}
                    </option>
                  ))}
                </select>
                <ChevronDown size={11} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-white/30" />
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-4xl px-6 py-6 space-y-5">

        {/* ── README summary ── */}
        {packData && Object.keys(packData.readme).length > 0 && (
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.015] p-5">
            <div className="mb-4 flex items-center gap-2">
              <FileSpreadsheet size={13} className="text-white/30" />
              <span className="text-[10px] font-semibold uppercase tracking-widest text-white/30">Pack summary</span>
            </div>
            {/* Prominent fields first */}
            <div className="grid grid-cols-2 gap-x-8 gap-y-3 md:grid-cols-3">
              {['Date', 'Founder', 'Posts', 'Pack'].map((key) =>
                packData.readme[key] ? (
                  <div key={key}>
                    <div className="text-[9px] uppercase tracking-widest text-white/25 mb-0.5">{key}</div>
                    <div className="text-sm text-white/75 leading-snug">{packData.readme[key]}</div>
                  </div>
                ) : null,
              )}
            </div>
            {/* Voice profile stats */}
            {packData.readme['Median word count'] && (
              <div className="mt-4 border-t border-white/[0.06] pt-4 grid grid-cols-2 gap-x-8 gap-y-2 md:grid-cols-3 text-xs">
                {['Median word count', 'Tagged cast rate', 'Hashtag rate'].map((key) =>
                  packData.readme[key] ? (
                    <div key={key} className="flex items-baseline gap-2">
                      <span className="text-[9px] uppercase tracking-widest text-white/20 shrink-0">{key.split(' ').slice(-2).join(' ')}</span>
                      <span className="text-white/45">{packData.readme[key]}</span>
                    </div>
                  ) : null,
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Loading ── */}
        {loadingData && (
          <div className="flex items-center justify-center py-24">
            <Loader2 size={20} className="animate-spin text-white/30" />
          </div>
        )}

        {/* ── Empty state ── */}
        {!loadingData && !loadingPacks && packs.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <FileSpreadsheet size={28} className="mb-4 text-white/15" />
            <p className="text-sm text-white/35">No post packs yet for {displayName}.</p>
            <p className="mt-1.5 text-xs text-white/20">
              Drop Excel files into{' '}
              <code className="rounded bg-white/8 px-1.5 py-0.5 text-[11px]">
                data/founders/{slug}/post-data/
              </code>
            </p>
          </div>
        )}

        {/* ── Source groups ── */}
        {!loadingData && grouped.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-white/30">
                {grouped.length} sources · {packData?.posts.length ?? 0} posts total
              </span>
            </div>
            {grouped.map(([sourceNum, posts], i) => (
              <SourceGroup
                key={sourceNum}
                sourceNum={sourceNum}
                posts={posts}
                headers={packData?.headers ?? []}
                defaultOpen={i === 0}
                onSelectPost={setSelectedPost}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Detail panel ── */}
      {selectedPost && (
        <DetailPanel
          post={selectedPost}
          headers={packData?.headers ?? []}
          onClose={() => setSelectedPost(null)}
        />
      )}
    </div>
  )
}
