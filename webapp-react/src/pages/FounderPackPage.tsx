import { useEffect, useState, useMemo } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft, FileSpreadsheet, Calendar, ChevronDown,
  Loader2, X, BookOpen, Quote, Sparkles,
} from 'lucide-react'
import clsx from 'clsx'
import { apiGet } from '../api/client'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Pack { filename: string; date: string; size_kb: number }
interface PackData { readme: Record<string, string>; headers: string[]; posts: Record<string, any>[] }

interface ColDef {
  key: string
  label: string
  group: string
  variantLetter?: 'A' | 'B' | 'C' | 'D' | 'E'
  width: number
  sticky?: boolean
  render?: 'status' | 'type' | 'variant-badge' | 'score-dots' | 'mono'
  truncate?: boolean
}

// ── Constants ─────────────────────────────────────────────────────────────────

const VARIANT_LETTERS = ['A', 'B', 'C', 'D', 'E'] as const

const VARIANT_ACCENT: Record<string, { header: string; cell: string; badge: string }> = {
  A: { header: 'bg-violet-950/50 text-violet-300/80', cell: 'bg-violet-950/30', badge: 'bg-violet-400 text-black' },
  B: { header: 'bg-sky-950/50 text-sky-300/80',       cell: 'bg-sky-950/30',    badge: 'bg-sky-400 text-black' },
  C: { header: 'bg-emerald-950/50 text-emerald-300/80', cell: 'bg-emerald-950/30', badge: 'bg-emerald-400 text-black' },
  D: { header: 'bg-amber-950/50 text-amber-300/80',   cell: 'bg-amber-950/30',  badge: 'bg-amber-400 text-black' },
  E: { header: 'bg-rose-950/50 text-rose-300/80',     cell: 'bg-rose-950/30',   badge: 'bg-rose-400 text-black' },
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function s(val: any): string { return val === null || val === undefined ? '' : String(val) }

function statusColor(value: string): string {
  const v = value.toLowerCase()
  if (v.includes('approved') || v.includes('done') || v.includes('final'))
    return 'bg-emerald-950/60 text-emerald-400 border-emerald-800/40'
  if (v.includes('pending') || v.includes('review'))
    return 'bg-amber-950/60 text-amber-400 border-amber-800/40'
  if (v.includes('reject') || v.includes('no'))
    return 'bg-red-950/60 text-red-400 border-red-800/40'
  if (v.includes('draft') || v.includes('wip'))
    return 'bg-sky-950/60 text-sky-400 border-sky-800/40'
  return 'bg-white/[0.04] text-white/45 border-white/[0.08]'
}

function groupHeaderClass(group: string): string {
  for (const v of VARIANT_LETTERS) {
    if (group === `Variant ${v}`) return VARIANT_ACCENT[v].header
  }
  return 'bg-[#0d0d0d] text-white/40'
}

function buildColDefs(headers: string[]): ColDef[] {
  function res(...candidates: string[]): string {
    for (const c of candidates) {
      if (headers.includes(c)) return c
    }
    return candidates[0]
  }

  const statusCols = headers.filter(h => h.startsWith('Status')).map(sh => ({
    key: sh,
    label: sh.replace(/^Status\s*/, '').replace(/[()]/g, '').trim() || sh,
    group: 'Core',
    width: 120,
    render: 'status' as const,
  }))

  return [
    { key: 'Row #',             label: 'Row #',         group: 'Core',     width: 52,  sticky: true, render: 'mono' },
    { key: res('File'),         label: 'File',           group: 'Core',     width: 80,  truncate: true },
    { key: res('Source #'),     label: 'Src #',          group: 'Core',     width: 56,  render: 'mono' },
    { key: res('Type'),         label: 'Type',           group: 'Core',     width: 72,  render: 'type' },
    ...statusCols,
    { key: res('Post Topic (derived from body)'), label: 'Topic', group: 'Content', width: 160, truncate: true },
    { key: res('Domain'),       label: 'Domain',         group: 'Content',  width: 100, truncate: true },
    { key: res('Kind'),         label: 'Kind',           group: 'Content',  width: 80 },
    { key: res('Final Post'),   label: 'Final Post',     group: 'Content',  width: 220, truncate: true },
    { key: res('Finalized Post'), label: 'Finalized',    group: 'Content',  width: 220, truncate: true },
    { key: res('Current Score (pts)'), label: 'Score',   group: 'Content',  width: 70 },
    { key: res('Source Quote'), label: 'Source Quote',   group: 'Source',   width: 200, truncate: true },
    { key: res('Mechanic'),     label: 'Mechanic',       group: 'Source',   width: 120, truncate: true },
    { key: res('Original Opening'), label: 'Orig. Opening', group: 'Source', width: 180, truncate: true },
    { key: res('Original Type'), label: 'Orig. Type',   group: 'Source',   width: 100 },
    { key: res("Buried Gold (from this post's paras 2-4)"), label: 'Buried Gold', group: 'Analysis', width: 200, truncate: true },
    { key: res('Weakness'),     label: 'Weakness',       group: 'Analysis', width: 180, truncate: true },
    { key: res('Recommended'),  label: 'Rec.',           group: 'Analysis', width: 72,  render: 'variant-badge' },
    { key: res('Why'),          label: 'Why',            group: 'Analysis', width: 200, truncate: true },
    ...VARIANT_LETTERS.flatMap(v => [
      { key: res(`${v}, Opening`,      `${v} - Opening`),      label: 'Opening',    group: `Variant ${v}`, variantLetter: v, width: 200, truncate: true },
      { key: res(`${v}, Rewrite Type`, `${v} - Rewrite Type`), label: 'Type',       group: `Variant ${v}`, variantLetter: v, width: 120 },
      { key: res(`${v}, Key Change`,   `${v} - Key Change`),   label: 'Key Change', group: `Variant ${v}`, variantLetter: v, width: 160, truncate: true },
      { key: res(`${v}, Expected Lift`,`${v} - Expected Lift`),label: 'Lift',       group: `Variant ${v}`, variantLetter: v, width: 72, render: 'score-dots' as const },
    ]),
  ]
}

// ── Small components ──────────────────────────────────────────────────────────

function StatusPill({ value }: { value: string }) {
  if (!value) return null
  return (
    <span className={clsx('inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium border whitespace-nowrap', statusColor(value))}>
      {value}
    </span>
  )
}

function TypeBadge({ type }: { type: string }) {
  if (!type) return null
  return (
    <span className="inline-flex h-5 min-w-[2.25rem] items-center justify-center rounded bg-white/[0.08] font-mono text-[10px] font-semibold text-white/55 px-1.5 whitespace-nowrap">
      {type}
    </span>
  )
}

function ScoreDots({ score }: { score: number }) {
  return (
    <span className="inline-flex gap-[3px] items-center">
      {[1, 2, 3, 4, 5].map(i => (
        <span key={i} className={clsx('h-1.5 w-1.5 rounded-full', i <= score ? 'bg-white/70' : 'bg-white/10')} />
      ))}
    </span>
  )
}

function VariantBadge({ letter }: { letter: string }) {
  const accent = VARIANT_ACCENT[letter.toUpperCase()]
  if (!accent) return <span className="text-white/40 text-xs font-mono">{letter}</span>
  return (
    <span className={clsx('inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold shrink-0', accent.badge)}>
      {letter.toUpperCase()}
    </span>
  )
}

// ── CellContent ───────────────────────────────────────────────────────────────

function CellContent({ col, val }: { col: ColDef; val: any }) {
  const text = s(val)

  switch (col.render) {
    case 'status':  return text ? <StatusPill value={text} /> : <span className="text-white/15">—</span>
    case 'type':    return text ? <TypeBadge type={text} /> : <span className="text-white/15">—</span>
    case 'variant-badge': return text ? <VariantBadge letter={text} /> : <span className="text-white/15">—</span>
    case 'score-dots': {
      const n = Number(text)
      return n > 0 ? <ScoreDots score={n} /> : <span className="text-white/15">—</span>
    }
    case 'mono': return <span className="font-mono text-[10px] text-white/30">{text || '—'}</span>
    default:
      if (!text) return <span className="text-white/15">—</span>
      if (col.truncate) {
        return (
          <div className="overflow-hidden text-ellipsis whitespace-nowrap text-xs text-white/65" title={text}>
            {text}
          </div>
        )
      }
      return <span className="text-xs text-white/65 break-words">{text}</span>
  }
}

// ── PackSummary ───────────────────────────────────────────────────────────────

function PackSummary({ readme }: { readme: Record<string, string> }) {
  const primary = [
    { key: 'Posts', label: 'Total Posts' },
    { key: 'Date', label: 'Pack Date' },
    { key: 'Founder', label: 'Founder' },
    { key: 'Pack', label: 'Pack' },
  ].filter(x => readme[x.key])

  const voice = [
    { key: 'Median word count', label: 'Med. words' },
    { key: 'Tagged cast rate', label: 'Tagged cast' },
    { key: 'Hashtag rate', label: 'Hashtag rate' },
  ].filter(x => readme[x.key])

  if (primary.length === 0) return null

  return (
    <div className="shrink-0 border-b border-white/[0.07] bg-[#040404] px-6 py-3.5 flex items-center gap-8 flex-wrap">
      {primary.map(({ key, label }) => (
        <div key={key}>
          <div className="text-[9px] uppercase tracking-widest text-white/20 mb-0.5">{label}</div>
          <div className="font-[var(--font-display)] text-xl font-bold text-white leading-none">{readme[key]}</div>
        </div>
      ))}
      {voice.length > 0 && (
        <>
          <div className="h-7 w-px bg-white/[0.08] hidden sm:block" />
          {voice.map(({ key, label }) => (
            <div key={key}>
              <div className="text-[9px] uppercase tracking-widest text-white/20 mb-0.5">{label}</div>
              <div className="text-sm text-white/45">{readme[key]}</div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

// ── TableHeader ───────────────────────────────────────────────────────────────

function TableHeader({ colDefs }: { colDefs: ColDef[] }) {
  const stickyCol = colDefs.find(c => c.sticky)
  const nonSticky = colDefs.filter(c => !c.sticky)

  const groups: { label: string; count: number }[] = []
  for (const col of nonSticky) {
    const last = groups[groups.length - 1]
    if (last && last.label === col.group) last.count++
    else groups.push({ label: col.group, count: 1 })
  }

  return (
    <thead className="sticky top-0 z-20">
      <tr>
        {stickyCol && (
          <th
            rowSpan={2}
            className="sticky left-0 z-30 border-b-2 border-r border-b-white/[0.12] border-r-white/[0.06] bg-[#0d0d0d] px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-white/30 text-left align-middle whitespace-nowrap"
            style={{ minWidth: stickyCol.width, width: stickyCol.width }}
          >
            {stickyCol.label}
          </th>
        )}
        {groups.map(({ label, count }) => (
          <th
            key={label}
            colSpan={count}
            className={clsx(
              'border-b border-r border-b-white/[0.06] border-r-white/[0.05] px-3 py-1.5 text-[10px] font-semibold text-left whitespace-nowrap',
              groupHeaderClass(label),
            )}
          >
            {label}
          </th>
        ))}
      </tr>
      <tr>
        {nonSticky.map(col => (
          <th
            key={col.key}
            style={col.truncate ? { minWidth: col.width, maxWidth: col.width, width: col.width } : { minWidth: col.width }}
            className="border-b-2 border-r border-b-white/[0.12] border-r-white/[0.04] bg-[#0d0d0d] px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-white/30 text-left whitespace-nowrap"
          >
            {col.label}
          </th>
        ))}
      </tr>
    </thead>
  )
}

// ── TableRow ──────────────────────────────────────────────────────────────────

function TableRow({
  post,
  colDefs,
  isSelected,
  onClick,
}: {
  post: Record<string, any>
  colDefs: ColDef[]
  isSelected: boolean
  onClick: () => void
}) {
  const rec = s(post['Recommended']).trim().toUpperCase()
  const stickyCol = colDefs.find(c => c.sticky)
  const nonSticky = colDefs.filter(c => !c.sticky)

  return (
    <tr
      onClick={onClick}
      className={clsx(
        'group cursor-pointer border-b border-white/[0.04] transition-colors',
        isSelected ? 'bg-white/[0.05]' : 'hover:bg-white/[0.025]',
      )}
    >
      {stickyCol && (
        <td
          className={clsx(
            'sticky left-0 z-10 border-r px-3 py-2.5 align-middle whitespace-nowrap',
            isSelected
              ? 'border-l-2 border-l-white/40 border-r-white/[0.08] bg-[#121212]'
              : 'border-r-white/[0.06] bg-[#0a0a0a] group-hover:bg-[#0f0f0f]',
          )}
          style={{ minWidth: stickyCol.width, width: stickyCol.width }}
        >
          <span className="font-mono text-[10px] text-white/30">{s(post[stickyCol.key]) || '—'}</span>
        </td>
      )}

      {nonSticky.map(col => {
        const isRecCell = col.variantLetter !== undefined && col.variantLetter === rec
        return (
          <td
            key={col.key}
            style={col.truncate ? { minWidth: col.width, maxWidth: col.width, width: col.width } : { minWidth: col.width }}
            className={clsx(
              'border-r border-white/[0.04] px-3 py-2.5 align-middle',
              isRecCell ? VARIANT_ACCENT[col.variantLetter!].cell : '',
            )}
          >
            <CellContent col={col} val={post[col.key]} />
          </td>
        )
      })}
    </tr>
  )
}

// ── PostTable ─────────────────────────────────────────────────────────────────

function PostTable({
  posts,
  headers,
  selectedPost,
  onSelectRow,
}: {
  posts: Record<string, any>[]
  headers: string[]
  selectedPost: Record<string, any> | null
  onSelectRow: (p: Record<string, any> | null) => void
}) {
  const colDefs = useMemo(() => buildColDefs(headers), [headers])

  return (
    <div className="h-full overflow-x-auto overflow-y-auto">
      <table className="w-max border-separate border-spacing-0 text-left">
        <TableHeader colDefs={colDefs} />
        <tbody>
          {posts.map((post, i) => (
            <TableRow
              key={s(post['Row #']) || i}
              post={post}
              colDefs={colDefs}
              isSelected={selectedPost === post}
              onClick={() => onSelectRow(selectedPost === post ? null : post)}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── DetailPanel ───────────────────────────────────────────────────────────────

function DetailPanel({
  post,
  headers,
  onClose,
}: {
  post: Record<string, any>
  headers: string[]
  onClose: () => void
}) {
  const rec         = s(post['Recommended']).trim().toUpperCase()
  const statusCols  = headers.filter(h => h.startsWith('Status'))
  const finalPost   = s(post['Finalized Post'] || post['Final Post'])
  const whyText     = s(post['Why'])
  const sourceQ     = s(post['Source Quote'])
  const mechanic    = s(post['Mechanic'])
  const origOpening = s(post['Original Opening'])
  const origType    = s(post['Original Type'])
  const topic       = s(post['Post Topic (derived from body)'])
  const domain      = s(post['Domain'])
  const kind        = s(post['Kind'])
  const score       = s(post['Current Score (pts)'])
  const buried      = s(post["Buried Gold (from this post's paras 2-4)"])
  const weakness    = s(post['Weakness'])

  const variants = VARIANT_LETTERS.map(v => ({
    letter: v,
    opening: s(post[`${v}, Opening`] ?? post[`${v} - Opening`]),
    type:    s(post[`${v}, Rewrite Type`] ?? post[`${v} - Rewrite Type`]),
    change:  s(post[`${v}, Key Change`] ?? post[`${v} - Key Change`]),
    lift:    Number(post[`${v}, Expected Lift`] ?? post[`${v} - Expected Lift`]) || 0,
  })).filter(v => v.opening)

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-end bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative flex h-screen w-full max-w-2xl flex-col bg-[#0a0a0a] border-l border-white/10 animate-slide-in-right"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 px-6 py-3.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-[10px] text-white/25">#{s(post['Row #'])}</span>
            <TypeBadge type={s(post['Type'])} />
            {rec && <VariantBadge letter={rec} />}
            {statusCols.map(col => post[col] ? <StatusPill key={col} value={s(post[col])} /> : null)}
          </div>
          <button onClick={onClose} className="shrink-0 text-white/25 hover:text-white transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="space-y-5 p-6">

            {finalPost && (
              <section>
                <div className="mb-2 flex items-center gap-2 text-[9px] font-semibold uppercase tracking-widest text-white/25">
                  <BookOpen size={10} /> Finalized Post
                </div>
                <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm text-white/85 leading-[1.85] whitespace-pre-wrap">
                  {finalPost}
                </div>
              </section>
            )}

            {whyText && (
              <section>
                <div className="mb-2 flex items-center gap-2 text-[9px] font-semibold uppercase tracking-widest text-white/25">
                  <Sparkles size={10} /> Why this variant wins
                </div>
                <p className="rounded-xl border border-white/[0.07] bg-white/[0.015] p-4 text-sm text-white/60 leading-relaxed italic">
                  {whyText}
                </p>
              </section>
            )}

            {variants.length > 0 && (
              <section>
                <div className="mb-3 text-[9px] font-semibold uppercase tracking-widest text-white/25">Opening Variants</div>
                <div className="space-y-2">
                  {variants.map(({ letter, opening, type, change, lift }) => {
                    const isRec = rec === letter
                    const accent = VARIANT_ACCENT[letter]
                    return (
                      <div key={letter} className={clsx(
                        'rounded-xl border p-4',
                        isRec ? `${accent.cell} border-white/20` : 'border-white/[0.07] bg-white/[0.015]',
                      )}>
                        <div className="mb-2.5 flex items-center gap-2.5 flex-wrap">
                          <VariantBadge letter={letter} />
                          {type && <span className="text-[10px] text-white/30">{type}</span>}
                          {lift > 0 && <ScoreDots score={lift} />}
                          {isRec && (
                            <span className="text-[9px] font-medium text-white/50 bg-white/[0.07] rounded-full px-2 py-0.5">
                              Recommended
                            </span>
                          )}
                        </div>
                        <p className={clsx('text-sm leading-snug pl-7', isRec ? 'text-white/85' : 'text-white/60')}>
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

            {origOpening && (
              <section>
                <div className="mb-2 text-[9px] font-semibold uppercase tracking-widest text-white/25">Original Opening</div>
                <blockquote className="border-l-2 border-white/15 bg-white/[0.015] rounded-r-xl py-3 pl-4 pr-4 text-sm text-white/45 leading-relaxed italic">
                  {origOpening}
                </blockquote>
                {origType && <p className="mt-1.5 text-[10px] text-white/25">Type: {origType}</p>}
              </section>
            )}

            {sourceQ && (
              <section>
                <div className="mb-2 flex items-center gap-2 text-[9px] font-semibold uppercase tracking-widest text-white/25">
                  <Quote size={10} /> Source
                </div>
                <blockquote className="border-l-2 border-white/10 bg-white/[0.015] rounded-r-xl py-3 pl-4 pr-4 text-xs text-white/40 leading-relaxed italic">
                  {sourceQ}
                </blockquote>
                {mechanic && <p className="mt-1.5 text-[10px] text-white/25">Mechanic: {mechanic}</p>}
              </section>
            )}

            {(topic || domain || kind || score || buried || weakness) && (
              <section>
                <div className="mb-3 text-[9px] font-semibold uppercase tracking-widest text-white/25">Analysis</div>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: 'Topic',  value: topic },
                    { label: 'Domain', value: domain },
                    { label: 'Kind',   value: kind },
                    { label: 'Score',  value: score },
                  ].filter(x => x.value).map(({ label, value }) => (
                    <div key={label} className="rounded-lg border border-white/[0.07] bg-white/[0.015] p-2.5">
                      <div className="text-[8px] uppercase tracking-widest text-white/20 mb-0.5">{label}</div>
                      <div className="text-xs text-white/60 leading-snug">{value}</div>
                    </div>
                  ))}
                  {buried && (
                    <div className="col-span-2 rounded-lg border border-white/[0.07] bg-white/[0.015] p-2.5">
                      <div className="text-[8px] uppercase tracking-widest text-white/20 mb-0.5">Buried Gold</div>
                      <div className="text-xs text-white/50 leading-snug italic">{buried}</div>
                    </div>
                  )}
                  {weakness && (
                    <div className="col-span-2 rounded-lg border border-white/[0.07] bg-white/[0.015] p-2.5">
                      <div className="text-[8px] uppercase tracking-widest text-white/20 mb-0.5">Weakness</div>
                      <div className="text-xs text-white/45 leading-snug">{weakness}</div>
                    </div>
                  )}
                </div>
              </section>
            )}

            <details className="group/d">
              <summary className="cursor-pointer select-none list-none flex items-center gap-1.5 text-[10px] text-white/20 hover:text-white/40 transition-colors">
                <ChevronDown size={11} className="transition-transform group-open/d:rotate-180" />
                All fields
              </summary>
              <div className="mt-3 rounded-xl border border-white/[0.06] bg-white/[0.01] p-3 space-y-1.5">
                {headers.map(h => (
                  <div key={h} className="flex gap-2 text-[10px]">
                    <span className="font-mono text-white/20 shrink-0 min-w-0">{h}:</span>
                    <span className="text-white/40 break-all">{s(post[h]) || '—'}</span>
                  </div>
                ))}
              </div>
            </details>

          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function FounderPackPage() {
  const { slug } = useParams<{ slug: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  const [authed, setAuthed]             = useState<boolean | null>(null)
  const [packs, setPacks]               = useState<Pack[]>([])
  const [selectedDate, setSelectedDate] = useState<string>(searchParams.get('date') ?? '')
  const [packData, setPackData]         = useState<PackData | null>(null)
  const [loadingPacks, setLoadingPacks] = useState(true)
  const [loadingData, setLoadingData]   = useState(false)
  const [selectedPost, setSelectedPost] = useState<Record<string, any> | null>(null)

  useEffect(() => {
    apiGet('/api/admin/me')
      .then(() => setAuthed(true))
      .catch(() => { setAuthed(false); navigate('/admin/login', { replace: true }) })
  }, [navigate])

  useEffect(() => {
    if (!authed || !slug) return
    setLoadingPacks(true)
    apiGet<{ packs: Pack[] }>(`/api/admin/founders/${slug}/post-packs`)
      .then(d => {
        setPacks(d.packs)
        if (!selectedDate && d.packs.length > 0) setSelectedDate(d.packs[0].date)
      })
      .catch(() => {})
      .finally(() => setLoadingPacks(false))
  }, [authed, slug])

  useEffect(() => {
    if (!authed || !selectedDate || !slug) return
    setSearchParams({ date: selectedDate }, { replace: true })
    setLoadingData(true)
    setPackData(null)
    setSelectedPost(null)
    apiGet<PackData>(`/api/admin/founders/${slug}/post-packs/${selectedDate}`)
      .then(d => setPackData(d))
      .catch(() => {})
      .finally(() => setLoadingData(false))
  }, [authed, selectedDate, slug])

  const displayName = slug?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) ?? ''

  if (authed === null) {
    return (
      <div className="flex h-screen items-center justify-center bg-black">
        <Loader2 size={20} className="animate-spin text-white/25" />
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col bg-black text-white overflow-hidden">

      {/* Top nav */}
      <div className="shrink-0 border-b border-white/[0.08] bg-black/95 backdrop-blur">
        <div className="flex items-center justify-between gap-4 px-6 py-3.5">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/admin')}
              className="flex items-center gap-1.5 text-sm text-white/30 hover:text-white transition-colors"
            >
              <ArrowLeft size={13} /> Admin
            </button>
            <span className="text-white/12">/</span>
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-md bg-white/10 text-xs font-bold">
                {displayName.charAt(0)}
              </div>
              <span className="font-[var(--font-display)] font-semibold text-sm">{displayName}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Calendar size={12} className="text-white/25" />
            {loadingPacks ? (
              <Loader2 size={12} className="animate-spin text-white/25" />
            ) : packs.length === 0 ? (
              <span className="text-xs text-white/20">No packs yet</span>
            ) : (
              <div className="relative">
                <select
                  value={selectedDate}
                  onChange={e => setSelectedDate(e.target.value)}
                  className="appearance-none rounded-lg border border-white/10 bg-white/[0.04] pl-3 pr-7 py-1.5 text-xs text-white focus:outline-none focus:border-white/25 cursor-pointer"
                >
                  {packs.map(p => (
                    <option key={p.date} value={p.date} className="bg-black">
                      {p.date} — {p.filename}
                    </option>
                  ))}
                </select>
                <ChevronDown size={10} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-white/25" />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Pack summary */}
      {packData && <PackSummary readme={packData.readme} />}

      {/* Row count bar */}
      {packData && !loadingData && (
        <div className="shrink-0 border-b border-white/[0.05] bg-[#040404] px-6 py-2 flex items-center gap-2">
          <FileSpreadsheet size={10} className="text-white/20" />
          <span className="text-[10px] text-white/20">
            {packData.posts.length} posts · {packData.headers.length} columns · click any row to expand
          </span>
        </div>
      )}

      {/* Main */}
      <div className="flex-1 overflow-hidden relative">
        {loadingData && (
          <div className="flex items-center justify-center h-full">
            <Loader2 size={20} className="animate-spin text-white/20" />
          </div>
        )}

        {!loadingData && !loadingPacks && packs.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <FileSpreadsheet size={28} className="mb-4 text-white/10" />
            <p className="text-sm text-white/30">No post packs yet for {displayName}.</p>
            <p className="mt-1.5 text-xs text-white/20">
              Drop Excel files into{' '}
              <code className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[11px] font-mono">
                data/founders/{slug}/post-data/
              </code>
            </p>
          </div>
        )}

        {!loadingData && packData && (
          <PostTable
            posts={packData.posts}
            headers={packData.headers}
            selectedPost={selectedPost}
            onSelectRow={setSelectedPost}
          />
        )}
      </div>

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
