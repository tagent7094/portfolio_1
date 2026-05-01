import { useEffect, useState, useMemo, useRef, useCallback, memo } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft, FileSpreadsheet, Calendar, ChevronDown,
  Loader2, X, BookOpen, Quote, Sparkles, Search,
  Download, Sheet, Sun, Moon, Eye, EyeOff,
} from 'lucide-react'
import clsx from 'clsx'
import * as XLSX from 'xlsx'
import { apiGet, apiPost } from '../api/client'
import { useTheme } from '../hooks/useTheme'

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
  render?: 'status' | 'status-editable' | 'type' | 'variant-badge' | 'score-dots' | 'mono'
  truncate?: boolean
}

// ── Constants ─────────────────────────────────────────────────────────────────

const VARIANT_LETTERS = ['A', 'B', 'C', 'D', 'E'] as const

const VARIANT_ACCENT: Record<string, { header: string; cell: string; badge: string; light: string }> = {
  A: { header: 'bg-violet-950/50 text-violet-300/80', cell: 'bg-violet-950/30', badge: 'bg-violet-400 text-black', light: 'bg-violet-100 border-violet-300' },
  B: { header: 'bg-sky-950/50 text-sky-300/80',       cell: 'bg-sky-950/30',    badge: 'bg-sky-400 text-black',    light: 'bg-sky-100 border-sky-300' },
  C: { header: 'bg-emerald-950/50 text-emerald-300/80', cell: 'bg-emerald-950/30', badge: 'bg-emerald-400 text-black', light: 'bg-emerald-100 border-emerald-300' },
  D: { header: 'bg-amber-950/50 text-amber-300/80',   cell: 'bg-amber-950/30',  badge: 'bg-amber-400 text-black',  light: 'bg-amber-100 border-amber-300' },
  E: { header: 'bg-rose-950/50 text-rose-300/80',     cell: 'bg-rose-950/30',   badge: 'bg-rose-400 text-black',   light: 'bg-rose-100 border-rose-300' },
}

const ALL_GROUPS = ['Core', 'Content', 'Source', 'Analysis', 'Variant A', 'Variant B', 'Variant C', 'Variant D', 'Variant E', 'Extra']

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
  // Returns the first candidate that actually exists in headers, or null if none match.
  function res(...candidates: string[]): string | null {
    for (const c of candidates) { if (headers.includes(c)) return c }
    return null
  }
  // Like res() but with fallback — used only for cols that must always appear (Row #, variants).
  function req(...candidates: string[]): string {
    return res(...candidates) ?? candidates[0]
  }

  const statusCols = headers.filter(h => h.startsWith('Status')).map(sh => ({
    key: sh,
    label: sh.replace(/^Status\s*/, '').replace(/[()]/g, '').trim() || sh,
    group: 'Core',
    width: 130,
    render: 'status-editable' as const,
  }))

  // Only add a structured col when its key actually exists in the data.
  function col(
    key: string | null,
    label: string,
    group: string,
    width: number,
    extra?: Partial<ColDef>,
  ): ColDef | null {
    if (!key) return null
    return { key, label, group, width, ...extra }
  }

  const structured: (ColDef | null)[] = [
    { key: 'Row #', label: 'Row #', group: 'Core', width: 52, sticky: true, render: 'mono' },
    col(res('File'),           'File',         'Core',     80,  { truncate: true }),
    col(res('Source #'),       'Src #',        'Core',     56,  { render: 'mono' }),
    col(res('Type'),           'Type',         'Core',     72,  { render: 'type' }),
    ...statusCols,
    col(res('Post Topic (derived from body)', 'Post Topic', 'Topic'), 'Topic', 'Content', 160, { truncate: true }),
    col(res('Domain'),         'Domain',       'Content', 100, { truncate: true }),
    col(res('Kind'),           'Kind',         'Content',  80),
    col(res('Final Post'),     'Final Post',   'Content', 220, { truncate: true }),
    col(res('Finalized Post'), 'Finalized',    'Content', 220, { truncate: true }),
    col(res('Current Score (pts)', 'Score'), 'Score', 'Content', 70),
    col(res('Source Quote'),   'Source Quote', 'Source',  200, { truncate: true }),
    col(res('Mechanic'),       'Mechanic',     'Source',  120, { truncate: true }),
    col(res('Original Opening'), 'Orig. Opening', 'Source', 180, { truncate: true }),
    col(res('Original Type'),  'Orig. Type',   'Source',  100),
    col(res("Buried Gold (from this post's paras 2-4)", 'Buried Gold'), 'Buried Gold', 'Analysis', 200, { truncate: true }),
    col(res('Weakness'),       'Weakness',     'Analysis', 180, { truncate: true }),
    col(res('Recommended'),    'Rec.',         'Analysis',  72, { render: 'variant-badge' }),
    col(res('Why'),            'Why',          'Analysis', 200, { truncate: true }),
    ...VARIANT_LETTERS.flatMap(v => [
      col(res(`${v}, Opening`,      `${v} - Opening`),      'Opening',    `Variant ${v}`, 200, { variantLetter: v, truncate: true }),
      col(res(`${v}, Rewrite Type`, `${v} - Rewrite Type`), 'Type',       `Variant ${v}`, 120, { variantLetter: v }),
      col(res(`${v}, Key Change`,   `${v} - Key Change`),   'Key Change', `Variant ${v}`, 160, { variantLetter: v, truncate: true }),
      col(res(`${v}, Expected Lift`,`${v} - Expected Lift`),'Lift',       `Variant ${v}`,  72, { variantLetter: v, render: 'score-dots' }),
    ] as (ColDef | null)[]),
  ]

  const definedCols = structured.filter((c): c is ColDef => c !== null)

  // Append any header not already covered — guarantees all Excel data is visible.
  const mappedKeys = new Set(definedCols.map(c => c.key))
  const extraCols: ColDef[] = headers
    .filter(h => !mappedKeys.has(h))
    .map(h => ({ key: h, label: h, group: 'Extra', width: 160, truncate: true }))

  return [...definedCols, ...extraCols]
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
    <span
      className="inline-flex h-5 min-w-[2.25rem] items-center justify-center rounded font-mono text-[10px] font-semibold px-1.5 whitespace-nowrap"
      style={{ backgroundColor: 'var(--surface-3)', color: 'var(--text-secondary)' }}
    >
      {type}
    </span>
  )
}

function ScoreDots({ score }: { score: number }) {
  return (
    <span className="inline-flex gap-[3px] items-center">
      {[1, 2, 3, 4, 5].map(i => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: i <= score ? 'var(--text-secondary)' : 'var(--border-1)' }}
        />
      ))}
    </span>
  )
}

function VariantBadge({ letter }: { letter: string }) {
  const accent = VARIANT_ACCENT[letter.toUpperCase()]
  if (!accent) return <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>{letter}</span>
  return (
    <span className={clsx('inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold shrink-0', accent.badge)}>
      {letter.toUpperCase()}
    </span>
  )
}

// ── Editable status cell ──────────────────────────────────────────────────────

const STATUS_OPTIONS = ['', 'Approved', 'Pending', 'Review', 'Rejected', 'Draft', 'WIP', 'Final', 'Done']

function EditableStatusCell({
  colKey,
  rowId,
  original,
  edits,
  onEdit,
}: {
  colKey: string
  rowId: string
  original: string
  edits: Record<string, Record<string, string>>
  onEdit: (rowId: string, colKey: string, value: string) => void
}) {
  const cellKey = `${rowId}__${colKey}`
  const edited = edits[rowId]?.[colKey]
  const value = edited !== undefined ? edited : original
  const isDirty = edited !== undefined && edited !== original
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={ref} className="relative" key={cellKey}>
      <button
        onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        className="group/edit flex items-center gap-1 w-full text-left"
        title="Click to edit"
      >
        {value
          ? <StatusPill value={value} />
          : <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>—</span>
        }
        {isDirty && <span className="h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" title="Edited" />}
      </button>
      {open && (
        <div
          className="absolute top-full left-0 z-50 mt-1 w-36 rounded-xl border border-white/15 bg-[#111] shadow-2xl py-1"
          onClick={e => e.stopPropagation()}
        >
          {STATUS_OPTIONS.map(opt => (
            <button
              key={opt || '__empty'}
              onClick={() => { onEdit(rowId, colKey, opt); setOpen(false) }}
              className={clsx(
                'w-full px-3 py-1.5 text-left text-[11px] hover:bg-white/[0.08] transition-colors',
                value === opt ? 'text-white' : 'text-white/50',
              )}
            >
              {opt || <span className="italic text-white/25">Clear</span>}
            </button>
          ))}
          <div className="border-t border-white/[0.07] mt-1 pt-1 px-2 pb-1">
            <input
              className="w-full rounded bg-white/[0.06] px-2 py-1 text-[11px] text-white/70 outline-none placeholder:text-white/20 focus:ring-1 focus:ring-white/20"
              placeholder="Custom…"
              defaultValue={value}
              onClick={e => e.stopPropagation()}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  onEdit(rowId, colKey, (e.target as HTMLInputElement).value)
                  setOpen(false)
                }
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

// ── CellContent ───────────────────────────────────────────────────────────────

function CellContent({
  col, val, rowId, edits, onEdit,
}: {
  col: ColDef; val: any; rowId: string
  edits: Record<string, Record<string, string>>
  onEdit: (rowId: string, colKey: string, value: string) => void
}) {
  const text = s(val)

  switch (col.render) {
    case 'status-editable':
      return (
        <EditableStatusCell
          colKey={col.key} rowId={rowId}
          original={text} edits={edits} onEdit={onEdit}
        />
      )
    case 'status':    return text ? <StatusPill value={text} /> : <span style={{ color: 'var(--text-faint)' }}>—</span>
    case 'type':      return text ? <TypeBadge type={text} /> : <span style={{ color: 'var(--text-faint)' }}>—</span>
    case 'variant-badge': return text ? <VariantBadge letter={text} /> : <span style={{ color: 'var(--text-faint)' }}>—</span>
    case 'score-dots': {
      const n = Number(text)
      return n > 0 ? <ScoreDots score={n} /> : <span style={{ color: 'var(--text-faint)' }}>—</span>
    }
    case 'mono': return (
      <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>{text || '—'}</span>
    )
    default:
      if (!text) return <span style={{ color: 'var(--text-faint)' }}>—</span>
      if (col.truncate) {
        return (
          <div className="overflow-hidden text-ellipsis whitespace-nowrap text-xs" style={{ color: 'var(--text-primary)' }} title={text}>
            {text}
          </div>
        )
      }
      return <span className="text-xs break-words" style={{ color: 'var(--text-primary)' }}>{text}</span>
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
    <div className="shrink-0 border-b px-6 py-3.5 flex items-center gap-8 flex-wrap"
      style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-1)' }}>
      {primary.map(({ key, label }) => (
        <div key={key}>
          <div className="text-[9px] uppercase tracking-widest mb-0.5" style={{ color: 'var(--text-faint)' }}>{label}</div>
          <div className="font-[var(--font-display)] text-xl font-bold leading-none" style={{ color: 'var(--text-primary)' }}>{readme[key]}</div>
        </div>
      ))}
      {voice.length > 0 && (
        <>
          <div className="h-7 w-px hidden sm:block" style={{ backgroundColor: 'var(--border-1)' }} />
          {voice.map(({ key, label }) => (
            <div key={key}>
              <div className="text-[9px] uppercase tracking-widest mb-0.5" style={{ color: 'var(--text-faint)' }}>{label}</div>
              <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>{readme[key]}</div>
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
            className="sticky left-0 z-30 border-b-2 border-r px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-left align-middle whitespace-nowrap"
            style={{
              minWidth: stickyCol.width, width: stickyCol.width,
              backgroundColor: 'var(--surface-2)',
              borderColor: 'var(--border-1)',
              color: 'var(--text-muted)',
            }}
          >
            {stickyCol.label}
          </th>
        )}
        {groups.map(({ label, count }) => (
          <th
            key={label}
            colSpan={count}
            className={clsx(
              'border-b border-r px-3 py-1.5 text-[10px] font-semibold text-left whitespace-nowrap',
              groupHeaderClass(label),
            )}
            style={{ borderColor: 'var(--border-2)' }}
          >
            {label}
          </th>
        ))}
      </tr>
      <tr>
        {nonSticky.map(col => (
          <th
            key={col.key}
            style={Object.assign(
              col.truncate ? { minWidth: col.width, maxWidth: col.width, width: col.width } : { minWidth: col.width },
              { backgroundColor: 'var(--surface-2)', borderColor: 'var(--border-1)', color: 'var(--text-muted)' },
            )}
            className="border-b-2 border-r px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-left whitespace-nowrap"
          >
            {col.label}
          </th>
        ))}
      </tr>
    </thead>
  )
}

// ── TableRow ──────────────────────────────────────────────────────────────────

const TableRow = memo(function TableRow({
  post, colDefs, isSelected, onClick, edits, onEdit,
}: {
  post: Record<string, any>
  colDefs: ColDef[]
  isSelected: boolean
  onClick: () => void
  edits: Record<string, Record<string, string>>
  onEdit: (rowId: string, colKey: string, value: string) => void
}) {
  const rec = s(post['Recommended']).trim().toUpperCase()
  const rowId = s(post['Row #']) || String(Math.random())
  const stickyCol = colDefs.find(c => c.sticky)
  const nonSticky = colDefs.filter(c => !c.sticky)

  return (
    <tr
      onClick={onClick}
      className="group cursor-pointer border-b transition-colors"
      style={{
        borderColor: 'var(--border-2)',
        backgroundColor: isSelected ? 'var(--row-selected)' : undefined,
      }}
      onMouseEnter={e => { if (!isSelected) (e.currentTarget as HTMLElement).style.backgroundColor = 'var(--row-hover)' }}
      onMouseLeave={e => { if (!isSelected) (e.currentTarget as HTMLElement).style.backgroundColor = '' }}
    >
      {stickyCol && (
        <td
          className="sticky left-0 z-10 border-r px-3 py-2.5 align-middle whitespace-nowrap"
          style={{
            minWidth: stickyCol.width, width: stickyCol.width,
            backgroundColor: isSelected ? 'var(--surface-3)' : 'var(--surface-1)',
            borderColor: 'var(--border-1)',
            borderLeft: isSelected ? '2px solid var(--text-muted)' : undefined,
          }}
        >
          <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {s(post[stickyCol.key]) || '—'}
          </span>
        </td>
      )}

      {nonSticky.map(col => {
        const isRecCell = col.variantLetter !== undefined && col.variantLetter === rec
        return (
          <td
            key={col.key}
            style={Object.assign(
              col.truncate ? { minWidth: col.width, maxWidth: col.width, width: col.width } : { minWidth: col.width },
              { borderColor: 'var(--border-2)' },
            )}
            className={clsx(
              'border-r px-3 py-2.5 align-middle',
              isRecCell ? VARIANT_ACCENT[col.variantLetter!].cell : '',
            )}
          >
            <CellContent col={col} val={post[col.key]} rowId={rowId} edits={edits} onEdit={onEdit} />
          </td>
        )
      })}
    </tr>
  )
})

// ── PostTable ─────────────────────────────────────────────────────────────────

function PostTable({
  posts, headers, selectedPost, onSelectRow, visibleGroups, edits, onEdit,
}: {
  posts: Record<string, any>[]
  headers: string[]
  selectedPost: Record<string, any> | null
  onSelectRow: (p: Record<string, any> | null) => void
  visibleGroups: Set<string>
  edits: Record<string, Record<string, string>>
  onEdit: (rowId: string, colKey: string, value: string) => void
}) {
  const allColDefs = useMemo(() => buildColDefs(headers), [headers])
  const colDefs = useMemo(
    () => allColDefs.filter(c => c.sticky || visibleGroups.has(c.group)),
    [allColDefs, visibleGroups],
  )

  return (
    <div className="h-full overflow-x-auto overflow-y-auto" style={{ backgroundColor: 'var(--page-bg)' }}>
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
              edits={edits}
              onEdit={onEdit}
            />
          ))}
        </tbody>
      </table>
      {posts.length === 0 && (
        <div className="flex items-center justify-center h-32 text-sm" style={{ color: 'var(--text-muted)' }}>
          No rows match your search.
        </div>
      )}
    </div>
  )
}

// ── DetailPanel ───────────────────────────────────────────────────────────────

function DetailPanel({
  post, headers, edits, onEdit, onClose,
}: {
  post: Record<string, any>
  headers: string[]
  edits: Record<string, Record<string, string>>
  onEdit: (rowId: string, colKey: string, value: string) => void
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
  const rowId       = s(post['Row #']) || String(Math.random())

  const variants = VARIANT_LETTERS.map(v => ({
    letter: v,
    opening: s(post[`${v}, Opening`] ?? post[`${v} - Opening`]),
    type:    s(post[`${v}, Rewrite Type`] ?? post[`${v} - Rewrite Type`]),
    change:  s(post[`${v}, Key Change`] ?? post[`${v} - Key Change`]),
    lift:    Number(post[`${v}, Expected Lift`] ?? post[`${v} - Expected Lift`]) || 0,
  })).filter(v => v.opening)

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-end backdrop-blur-sm"
      style={{ backgroundColor: 'rgba(0,0,0,0.65)' }}
      onClick={onClose}
    >
      <div
        className="relative flex h-screen w-full max-w-2xl flex-col border-l animate-slide-in-right"
        style={{ backgroundColor: 'var(--surface-1)', borderColor: 'var(--border-1)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between gap-3 border-b px-6 py-3.5"
          style={{ borderColor: 'var(--border-1)' }}>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-[10px]" style={{ color: 'var(--text-faint)' }}>#{s(post['Row #'])}</span>
            <TypeBadge type={s(post['Type'])} />
            {rec && <VariantBadge letter={rec} />}
            {statusCols.map(col => {
              const val = edits[rowId]?.[col] !== undefined ? edits[rowId][col] : s(post[col])
              return val ? <StatusPill key={col} value={val} /> : null
            })}
          </div>
          <button onClick={onClose} className="shrink-0 transition-colors hover:opacity-70" style={{ color: 'var(--text-muted)' }}>
            <X size={16} />
          </button>
        </div>

        {/* Status editing */}
        {statusCols.length > 0 && (
          <div className="shrink-0 border-b px-6 py-3 flex items-center gap-4 flex-wrap"
            style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)' }}>
            {statusCols.map(col => (
              <div key={col} className="flex items-center gap-2">
                <span className="text-[9px] uppercase tracking-widest" style={{ color: 'var(--text-faint)' }}>
                  {col.replace(/^Status\s*/, '').replace(/[()]/g, '').trim()}
                </span>
                <EditableStatusCell
                  colKey={col} rowId={rowId}
                  original={s(post[col])} edits={edits} onEdit={onEdit}
                />
              </div>
            ))}
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          <div className="space-y-5 p-6">

            {finalPost && (
              <section>
                <div className="mb-2 flex items-center gap-2 text-[9px] font-semibold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
                  <BookOpen size={10} /> Finalized Post
                </div>
                <div className="rounded-xl border p-4 text-sm leading-[1.85] whitespace-pre-wrap"
                  style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-2)', color: 'var(--text-primary)' }}>
                  {finalPost}
                </div>
              </section>
            )}

            {whyText && (
              <section>
                <div className="mb-2 flex items-center gap-2 text-[9px] font-semibold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
                  <Sparkles size={10} /> Why this variant wins
                </div>
                <p className="rounded-xl border p-4 text-sm leading-relaxed italic"
                  style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)', color: 'var(--text-secondary)' }}>
                  {whyText}
                </p>
              </section>
            )}

            {variants.length > 0 && (
              <section>
                <div className="mb-3 text-[9px] font-semibold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
                  Opening Variants
                </div>
                <div className="space-y-2">
                  {variants.map(({ letter, opening, type, change, lift }) => {
                    const isRec = rec === letter
                    const accent = VARIANT_ACCENT[letter]
                    return (
                      <div key={letter} className={clsx('rounded-xl border p-4', isRec ? `${accent.cell} border-white/20` : '')}
                        style={!isRec ? { borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)' } : {}}>
                        <div className="mb-2.5 flex items-center gap-2.5 flex-wrap">
                          <VariantBadge letter={letter} />
                          {type && <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{type}</span>}
                          {lift > 0 && <ScoreDots score={lift} />}
                          {isRec && (
                            <span className="text-[9px] font-medium rounded-full px-2 py-0.5"
                              style={{ backgroundColor: 'var(--surface-3)', color: 'var(--text-secondary)' }}>
                              Recommended
                            </span>
                          )}
                        </div>
                        <p className={clsx('text-sm leading-snug pl-7')} style={{ color: isRec ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                          {opening}
                        </p>
                        {change && (
                          <p className="mt-1.5 pl-7 text-[11px] italic" style={{ color: 'var(--text-muted)' }}>{change}</p>
                        )}
                      </div>
                    )
                  })}
                </div>
              </section>
            )}

            {origOpening && (
              <section>
                <div className="mb-2 text-[9px] font-semibold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Original Opening</div>
                <blockquote className="border-l-2 rounded-r-xl py-3 pl-4 pr-4 text-sm leading-relaxed italic"
                  style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-2)', color: 'var(--text-secondary)' }}>
                  {origOpening}
                </blockquote>
                {origType && <p className="mt-1.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>Type: {origType}</p>}
              </section>
            )}

            {sourceQ && (
              <section>
                <div className="mb-2 flex items-center gap-2 text-[9px] font-semibold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
                  <Quote size={10} /> Source
                </div>
                <blockquote className="border-l-2 rounded-r-xl py-3 pl-4 pr-4 text-xs leading-relaxed italic"
                  style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-2)', color: 'var(--text-secondary)' }}>
                  {sourceQ}
                </blockquote>
                {mechanic && <p className="mt-1.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>Mechanic: {mechanic}</p>}
              </section>
            )}

            {(topic || domain || kind || score || buried || weakness) && (
              <section>
                <div className="mb-3 text-[9px] font-semibold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Analysis</div>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: 'Topic', value: topic }, { label: 'Domain', value: domain },
                    { label: 'Kind', value: kind },   { label: 'Score', value: score },
                  ].filter(x => x.value).map(({ label, value }) => (
                    <div key={label} className="rounded-lg border p-2.5"
                      style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)' }}>
                      <div className="text-[8px] uppercase tracking-widest mb-0.5" style={{ color: 'var(--text-faint)' }}>{label}</div>
                      <div className="text-xs leading-snug" style={{ color: 'var(--text-secondary)' }}>{value}</div>
                    </div>
                  ))}
                  {buried && (
                    <div className="col-span-2 rounded-lg border p-2.5"
                      style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)' }}>
                      <div className="text-[8px] uppercase tracking-widest mb-0.5" style={{ color: 'var(--text-faint)' }}>Buried Gold</div>
                      <div className="text-xs leading-snug italic" style={{ color: 'var(--text-secondary)' }}>{buried}</div>
                    </div>
                  )}
                  {weakness && (
                    <div className="col-span-2 rounded-lg border p-2.5"
                      style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)' }}>
                      <div className="text-[8px] uppercase tracking-widest mb-0.5" style={{ color: 'var(--text-faint)' }}>Weakness</div>
                      <div className="text-xs leading-snug" style={{ color: 'var(--text-secondary)' }}>{weakness}</div>
                    </div>
                  )}
                </div>
              </section>
            )}

            <details className="group/d">
              <summary className="cursor-pointer select-none list-none flex items-center gap-1.5 text-[10px] transition-colors"
                style={{ color: 'var(--text-faint)' }}>
                <ChevronDown size={11} className="transition-transform group-open/d:rotate-180" />
                All fields
              </summary>
              <div className="mt-3 rounded-xl border p-3 space-y-1.5"
                style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)' }}>
                {headers.map(h => (
                  <div key={h} className="flex gap-2 text-[10px]">
                    <span className="font-mono shrink-0 min-w-0" style={{ color: 'var(--text-faint)' }}>{h}:</span>
                    <span className="break-all" style={{ color: 'var(--text-secondary)' }}>{s(post[h]) || '—'}</span>
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

// ── Export helpers ────────────────────────────────────────────────────────────

function buildExportRows(
  posts: Record<string, any>[],
  headers: string[],
  edits: Record<string, Record<string, string>>,
): Record<string, string>[] {
  return posts.map(post => {
    const rowId = s(post['Row #'])
    const row: Record<string, string> = {}
    for (const h of headers) {
      row[h] = edits[rowId]?.[h] !== undefined ? edits[rowId][h] : s(post[h])
    }
    return row
  })
}

function exportExcel(
  posts: Record<string, any>[],
  headers: string[],
  edits: Record<string, Record<string, string>>,
  filename: string,
) {
  const rows = buildExportRows(posts, headers, edits)
  const ws = XLSX.utils.json_to_sheet(rows, { header: headers })
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'Posts')
  XLSX.writeFile(wb, `${filename}.xlsx`)
}

async function exportToGoogleSheets(
  posts: Record<string, any>[],
  headers: string[],
  edits: Record<string, Record<string, string>>,
  sheetTitle: string,
  accessToken: string,
): Promise<string> {
  const rows = buildExportRows(posts, headers, edits)
  const values = [headers, ...rows.map(r => headers.map(h => r[h] || ''))]

  const createRes = await fetch('https://sheets.googleapis.com/v4/spreadsheets', {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ properties: { title: sheetTitle } }),
  })
  const sheet = await createRes.json()
  const spreadsheetId = sheet.spreadsheetId

  await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/A1:append?valueInputOption=RAW`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  })

  return `https://docs.google.com/spreadsheets/d/${spreadsheetId}`
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function FounderPackPage() {
  const { slug } = useParams<{ slug: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [theme, toggleTheme] = useTheme()

  const [authed, setAuthed]             = useState<boolean | null>(null)
  const [packs, setPacks]               = useState<Pack[]>([])
  const [selectedDate, setSelectedDate] = useState<string>(searchParams.get('date') ?? '')
  const [packData, setPackData]         = useState<PackData | null>(null)
  const [loadingPacks, setLoadingPacks] = useState(true)
  const [loadingData, setLoadingData]   = useState(false)
  const [selectedPost, setSelectedPost] = useState<Record<string, any> | null>(null)
  const [search, setSearch]             = useState('')
  const [visibleGroups, setVisibleGroups] = useState<Set<string>>(new Set(ALL_GROUPS))
  const [edits, setEdits]               = useState<Record<string, Record<string, string>>>({})
  const [saving, setSaving]             = useState(false)
  const [groupMenuOpen, setGroupMenuOpen] = useState(false)
  const [sheetExporting, setSheetExporting] = useState(false)

  const handleEdit = useCallback((rowId: string, colKey: string, value: string) => {
    setEdits(prev => ({
      ...prev,
      [rowId]: { ...(prev[rowId] || {}), [colKey]: value },
    }))
  }, [])

  const editCount = useMemo(
    () => Object.values(edits).reduce((sum, row) => sum + Object.keys(row).length, 0),
    [edits],
  )

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
    setEdits({})
    apiGet<PackData>(`/api/admin/founders/${slug}/post-packs/${selectedDate}`)
      .then(d => setPackData(d))
      .catch(() => {})
      .finally(() => setLoadingData(false))
  }, [authed, selectedDate, slug])

  const filteredPosts = useMemo(() => {
    if (!packData) return []
    const q = search.trim().toLowerCase()
    if (!q) return packData.posts
    return packData.posts.filter(post =>
      packData.headers.some(h => s(post[h]).toLowerCase().includes(q))
    )
  }, [packData, search])

  const toggleGroup = (g: string) => {
    setVisibleGroups(prev => {
      const next = new Set(prev)
      if (next.has(g)) next.delete(g)
      else next.add(g)
      return next
    })
  }

  const saveEdits = async () => {
    if (!packData || !slug || !selectedDate || editCount === 0) return
    setSaving(true)
    try {
      await apiPost(`/api/admin/founders/${slug}/post-packs/${selectedDate}/edits`, { edits })
    } catch {
      // silently ignore — edits are still in local state
    } finally {
      setSaving(false)
    }
  }

  const handleExcelExport = () => {
    if (!packData) return
    exportExcel(packData.posts, packData.headers, edits, `${slug}-${selectedDate}`)
  }

  const handleSheetsExport = async () => {
    if (!packData || !slug || !selectedDate) return
    setSheetExporting(true)
    try {
      const res = await apiPost<{ url: string }>(
        `/api/admin/founders/${slug}/post-packs/${selectedDate}/export-sheets`,
        { edits },
      )
      window.open(res.url, '_blank')
    } catch (e: any) {
      alert(`Google Sheets export failed: ${e?.message || 'unknown error'}`)
    } finally {
      setSheetExporting(false)
    }
  }

  const displayName = slug?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) ?? ''

  if (authed === null) {
    return (
      <div className="flex h-screen items-center justify-center" style={{ backgroundColor: 'var(--page-bg)' }}>
        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden" style={{ backgroundColor: 'var(--page-bg)', color: 'var(--text-primary)' }}>

      {/* ── Top nav ── */}
      <div className="shrink-0 border-b backdrop-blur" style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-1)' }}>
        <div className="flex items-center gap-3 px-4 py-2.5 flex-wrap">
          {/* Left: breadcrumb */}
          <button
            onClick={() => navigate('/admin')}
            className="flex items-center gap-1.5 text-sm transition-opacity hover:opacity-70"
            style={{ color: 'var(--text-muted)' }}
          >
            <ArrowLeft size={13} /> Admin
          </button>
          <span style={{ color: 'var(--text-faint)' }}>/</span>
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-md text-xs font-bold"
              style={{ backgroundColor: 'var(--surface-3)', color: 'var(--text-secondary)' }}>
              {displayName.charAt(0)}
            </div>
            <span className="font-[var(--font-display)] font-semibold text-sm">{displayName}</span>
          </div>

          <div className="flex-1" />

          {/* Right: controls */}
          <div className="flex items-center gap-2 flex-wrap">

            {/* Date picker */}
            <div className="flex items-center gap-2">
              <Calendar size={12} style={{ color: 'var(--text-muted)' }} />
              {loadingPacks ? (
                <Loader2 size={12} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
              ) : packs.length > 0 ? (
                <div className="relative">
                  <select
                    value={selectedDate}
                    onChange={e => setSelectedDate(e.target.value)}
                    className="appearance-none rounded-lg border pl-3 pr-7 py-1.5 text-xs focus:outline-none cursor-pointer"
                    style={{
                      borderColor: 'var(--border-1)',
                      backgroundColor: 'var(--surface-2)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    {packs.map(p => (
                      <option key={p.date} value={p.date}>{p.date} — {p.filename}</option>
                    ))}
                  </select>
                  <ChevronDown size={10} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
                </div>
              ) : null}
            </div>

            {/* Group toggle */}
            <div className="relative">
              <button
                onClick={() => setGroupMenuOpen(o => !o)}
                className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors"
                style={{ borderColor: 'var(--border-1)', color: 'var(--text-secondary)', backgroundColor: 'var(--surface-2)' }}
              >
                {visibleGroups.size < ALL_GROUPS.length ? <EyeOff size={12} /> : <Eye size={12} />}
                Columns
              </button>
              {groupMenuOpen && (
                <div
                  className="absolute right-0 top-full mt-1 z-50 rounded-xl border p-2 shadow-xl min-w-[160px]"
                  style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-1)' }}
                >
                  {ALL_GROUPS.map(g => (
                    <label key={g} className="flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer hover:opacity-70 text-xs">
                      <input
                        type="checkbox"
                        checked={visibleGroups.has(g)}
                        onChange={() => toggleGroup(g)}
                        className="accent-white"
                      />
                      <span style={{ color: 'var(--text-secondary)' }}>{g}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>

            {/* Save edits */}
            {editCount > 0 && (
              <button
                onClick={saveEdits}
                disabled={saving}
                className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors"
                style={{ borderColor: '#f59e0b', color: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.08)' }}
              >
                {saving ? <Loader2 size={12} className="animate-spin" /> : null}
                Save {editCount} edit{editCount !== 1 ? 's' : ''}
              </button>
            )}

            {/* Export Excel */}
            <button
              onClick={handleExcelExport}
              disabled={!packData}
              className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors disabled:opacity-40"
              style={{ borderColor: 'var(--border-1)', color: 'var(--text-secondary)', backgroundColor: 'var(--surface-2)' }}
            >
              <Download size={12} /> Excel
            </button>

            {/* Export to Google Sheets */}
            <button
              onClick={handleSheetsExport}
              disabled={!packData || sheetExporting}
              className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors disabled:opacity-40"
              style={{ borderColor: 'var(--border-1)', color: 'var(--text-secondary)', backgroundColor: 'var(--surface-2)' }}
              title="Export to Google Sheets (creates a new sheet, shares with content@tagent.club)"
            >
              {sheetExporting ? <Loader2 size={12} className="animate-spin" /> : <Sheet size={12} />}
              Sheets
            </button>

            {/* Theme toggle */}
            <button
              onClick={toggleTheme}
              className="flex items-center justify-center h-7 w-7 rounded-lg border transition-colors"
              style={{ borderColor: 'var(--border-1)', color: 'var(--text-secondary)', backgroundColor: 'var(--surface-2)' }}
              title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {theme === 'dark' ? <Sun size={13} /> : <Moon size={13} />}
            </button>
          </div>
        </div>

        {/* Search bar */}
        <div className="border-t px-4 py-2" style={{ borderColor: 'var(--border-2)' }}>
          <div className="relative max-w-sm">
            <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: 'var(--text-muted)' }} />
            <input
              type="text"
              placeholder="Search all columns…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full rounded-lg border pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:ring-1"
              style={{
                borderColor: 'var(--border-1)',
                backgroundColor: 'var(--surface-2)',
                color: 'var(--text-primary)',
              }}
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2 top-1/2 -translate-y-1/2"
                style={{ color: 'var(--text-muted)' }}
              >
                <X size={11} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Pack summary */}
      {packData && <PackSummary readme={packData.readme} />}

      {/* Row count bar */}
      {packData && !loadingData && (
        <div className="shrink-0 border-b px-4 py-2 flex items-center gap-3"
          style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-1)' }}>
          <FileSpreadsheet size={10} style={{ color: 'var(--text-faint)' }} />
          <span className="text-[10px]" style={{ color: 'var(--text-faint)' }}>
            {filteredPosts.length}{filteredPosts.length !== packData.posts.length ? ` of ${packData.posts.length}` : ''} posts
            · {packData.headers.length} columns
            {editCount > 0 && ` · ${editCount} unsaved edit${editCount !== 1 ? 's' : ''}`}
            · click row to expand
          </span>
        </div>
      )}

      {/* Main */}
      <div className="flex-1 overflow-hidden relative">
        {loadingData && (
          <div className="flex items-center justify-center h-full">
            <Loader2 size={20} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
          </div>
        )}

        {!loadingData && !loadingPacks && packs.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <FileSpreadsheet size={28} className="mb-4" style={{ color: 'var(--text-faint)' }} />
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No post packs yet for {displayName}.</p>
            <p className="mt-1.5 text-xs" style={{ color: 'var(--text-faint)' }}>
              Drop Excel files into{' '}
              <code className="rounded px-1.5 py-0.5 text-[11px] font-mono"
                style={{ backgroundColor: 'var(--surface-3)', color: 'var(--text-secondary)' }}>
                data/founders/{slug}/post-data/
              </code>
            </p>
          </div>
        )}

        {!loadingData && packData && (
          <PostTable
            posts={filteredPosts}
            headers={packData.headers}
            selectedPost={selectedPost}
            onSelectRow={setSelectedPost}
            visibleGroups={visibleGroups}
            edits={edits}
            onEdit={handleEdit}
          />
        )}
      </div>

      {selectedPost && packData && (
        <DetailPanel
          post={selectedPost}
          headers={packData.headers}
          edits={edits}
          onEdit={handleEdit}
          onClose={() => setSelectedPost(null)}
        />
      )}
    </div>
  )
}
