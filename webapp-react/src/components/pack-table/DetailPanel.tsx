import { X, BookOpen, Quote, Sparkles, ChevronDown } from 'lucide-react'
import clsx from 'clsx'
import { VARIANT_LETTERS, VARIANT_ACCENT } from './types'
import { s } from './helpers'
import { StatusPill, TypeBadge, VariantBadge, ScoreDots, EditableStatusCell } from './cells'

export function DetailPanel({
  post, headers, edits, onEdit, onClose, onSelectVariant,
}: {
  post: Record<string, any>
  headers: string[]
  edits: Record<string, Record<string, string>>
  onEdit: (rowId: string, colKey: string, value: string) => void
  onClose: () => void
  onSelectVariant?: (variantLetter: string, openerText: string, postBody: string) => void
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
  const buried      = s(post["Buried Gold (from this post's paras 2-4)"] || post['Buried Gold'])
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
      className="fixed inset-0 z-50 flex items-end sm:items-start sm:justify-end backdrop-blur-sm"
      style={{ backgroundColor: 'rgba(0,0,0,0.65)' }}
      onClick={onClose}
    >
      <div
        className="relative flex w-full max-w-2xl flex-col border-t sm:border-t-0 sm:border-l animate-slide-up sm:animate-slide-in-right"
        style={{
          backgroundColor: 'var(--surface-1)',
          borderColor: 'var(--border-1)',
          height: '90dvh',
          maxHeight: '90dvh',
        }}
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
                        {onSelectVariant && (
                          <button
                            onClick={() => onSelectVariant(letter, opening, finalPost)}
                            className="mt-2 ml-7 px-3 py-1.5 text-[10px] font-medium rounded-md transition-colors"
                            style={{
                              backgroundColor: 'var(--surface-3)',
                              color: 'var(--text-secondary)',
                              border: '1px solid var(--border-1)',
                            }}
                            onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--text-primary)'; e.currentTarget.style.color = 'var(--surface-1)' }}
                            onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'var(--surface-3)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
                          >
                            Use This
                          </button>
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
