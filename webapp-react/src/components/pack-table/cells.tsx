import { useState, useEffect, useRef } from 'react'
import clsx from 'clsx'
import type { ColDef } from './types'
import { VARIANT_ACCENT } from './types'
import { s, statusColor } from './helpers'

export function StatusPill({ value }: { value: string }) {
  if (!value) return null
  return (
    <span className={clsx('inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium border whitespace-nowrap', statusColor(value))}>
      {value}
    </span>
  )
}

export function TypeBadge({ type }: { type: string }) {
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

export function ScoreDots({ score }: { score: number }) {
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

export function VariantBadge({ letter }: { letter: string }) {
  const accent = VARIANT_ACCENT[letter.toUpperCase()]
  if (!accent) return <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>{letter}</span>
  return (
    <span className={clsx('inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold shrink-0', accent.badge)}>
      {letter.toUpperCase()}
    </span>
  )
}

const STATUS_OPTIONS = ['', 'Approved', 'Pending', 'Review', 'Rejected', 'Draft', 'WIP', 'Final', 'Done']

export function EditableStatusCell({
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

export function EditableTextCell({
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
  const edited = edits[rowId]?.[colKey]
  const value = edited !== undefined ? edited : original
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing && inputRef.current) inputRef.current.focus()
  }, [editing])

  if (!editing) {
    return (
      <button
        onClick={e => { e.stopPropagation(); setDraft(value); setEditing(true) }}
        className="w-full text-left text-[11px] min-h-[20px]"
        style={{ color: value ? 'var(--text-primary)' : 'var(--text-faint)' }}
        title="Click to edit"
      >
        {value || '—'}
      </button>
    )
  }

  return (
    <input
      ref={inputRef}
      className="w-full rounded bg-white/[0.06] px-1.5 py-0.5 text-[11px] text-white/80 outline-none placeholder:text-white/20 focus:ring-1 focus:ring-white/20"
      value={draft}
      onChange={e => setDraft(e.target.value)}
      onClick={e => e.stopPropagation()}
      onBlur={() => { onEdit(rowId, colKey, draft); setEditing(false) }}
      onKeyDown={e => {
        if (e.key === 'Enter') { onEdit(rowId, colKey, draft); setEditing(false) }
        if (e.key === 'Escape') setEditing(false)
      }}
      placeholder="Add feedback..."
    />
  )
}

export function CellContent({
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
    case 'editable-text':
      return (
        <EditableTextCell
          colKey={col.key} rowId={rowId}
          original={text} edits={edits} onEdit={onEdit}
        />
      )
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
