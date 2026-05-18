import { useState, useMemo, useEffect } from 'react'
import { X, ArrowLeftRight, Sparkles, Quote } from 'lucide-react'
import clsx from 'clsx'
import { VARIANT_LETTERS, VARIANT_ACCENT } from './types'
import { s } from './helpers'
import { StatusPill, TypeBadge, EditableStatusCell, ScoreDots } from './cells'

/**
 * Parallel-text comparison view.
 *
 * Layout:
 *   ┌── header (compact metadata + close + actions) ─────────────────────────┐
 *   │ SOURCE (left, sticky) ║ VARIANT TABS + FINAL POST (right, scrollable) │
 *   └───────────────────────────────────────────────────────────────────────┘
 *
 * Source is anchored on the left so the eye never has to chase context.
 * Variants surface as tabs at the top of the right column — one click swaps
 * the opener and shows a struck-through preview of the original.
 */
export function DetailPanel({
  post, headers, edits, onEdit, onClose, onSelectVariant, onSwapOpener,
}: {
  post: Record<string, any>
  headers: string[]
  edits: Record<string, Record<string, string>>
  onEdit: (rowId: string, colKey: string, value: string) => void
  onClose: () => void
  onSelectVariant?: (variantLetter: string, openerText: string, postBody: string) => void
  onSwapOpener?: (variantLetter: string, openerText: string, postBody: string) => void
}) {
  const rec         = s(post['Recommended']).trim().toUpperCase()
  const statusCols  = headers.filter(h => h.startsWith('Status'))
  const finalPost   = s(post['Finalized Post'] || post['Final Post'])
  const whyText     = s(post['Why'])
  // Source column lookup — canonical key from BATCH_HEADERS is "Source Post",
  // but earlier manual xlsx uploads named it "Source Quote". Accept either.
  const sourceQ     = s(post['Source Post'] || post['Source Quote'])
  const mechanic    = s(post['Mechanic'])
  const origOpening = s(post['Original Opening'])
  const origType    = s(post['Original Type'])
  const topic       = s(post['Post Topic (derived from body)'])
  const domain      = s(post['Domain'])
  const kind        = s(post['Kind'])
  const score       = s(post['Current Score (pts)'])
  const buried      = s(post["Buried Gold (from this post's paras 2-4)"] || post['Buried Gold'])
  const weakness    = s(post['Weakness'])
  const entryDoor   = s(post['Entry Door'])
  const mode        = s(post['Mode'])
  const wordCount   = s(post['Word Count'])
  const rowId       = s(post['Row #']) || String(Math.random())

  const variants = useMemo(() => VARIANT_LETTERS.map(v => ({
    letter: v,
    opening: s(post[`Variant ${v} Opening`] ?? post[`${v}, Opening`] ?? post[`${v} - Opening`]),
    type:    s(post[`Variant ${v} Rewrite Type`] ?? post[`${v}, Rewrite Type`] ?? post[`${v} - Rewrite Type`]),
    change:  s(post[`Variant ${v} Key Change`] ?? post[`${v}, Key Change`] ?? post[`${v} - Key Change`]),
    lift:    Number(post[`Variant ${v} Expected Lift`] ?? post[`${v}, Expected Lift`] ?? post[`${v} - Expected Lift`]) || 0,
  })).filter(v => v.opening), [post])

  // Active opener — defaults to recommended variant, falls back to "orig" view.
  const initialActive: string = rec && variants.some(v => v.letter === rec) ? rec : (variants[0]?.letter || 'ORIG')
  const [active, setActive] = useState<string>(initialActive)
  useEffect(() => { setActive(initialActive) }, [rowId, initialActive])

  const activeVariant = variants.find(v => v.letter === active)
  // Construct the "preview body" — swap paragraph[0] with the active variant's opener.
  const displayedBody = useMemo(() => {
    if (!finalPost) return ''
    if (active === 'ORIG' || !activeVariant) return finalPost
    const paragraphs = finalPost.split(/\n\n+/)
    if (paragraphs.length === 0) return activeVariant.opening
    paragraphs[0] = activeVariant.opening
    return paragraphs.join('\n\n')
  }, [active, activeVariant, finalPost])

  const activeAccent = activeVariant ? VARIANT_ACCENT[activeVariant.letter] : null

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-center p-3 sm:p-5 lg:p-8"
      style={{ backgroundColor: 'rgba(8,9,12,0.78)', backdropFilter: 'blur(6px)' }}
      onClick={onClose}
    >
      <div
        className="relative flex flex-col w-full max-w-[1440px] overflow-hidden rounded-2xl border shadow-2xl animate-scale-in"
        style={{
          backgroundColor: 'var(--surface-1)',
          borderColor: 'var(--border-1)',
          boxShadow: '0 30px 90px -20px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* ─── HEADER ─────────────────────────────────────────────────────── */}
        <header
          className="flex shrink-0 items-center justify-between gap-4 border-b px-5 py-3"
          style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-2)' }}
        >
          <div className="flex items-center gap-3 flex-wrap">
            <span
              className="font-mono text-[10px] tracking-wider px-2 py-1 rounded-md"
              style={{ color: 'var(--text-primary)', backgroundColor: 'var(--surface-3)' }}
            >
              #{s(post['Row #'])}
            </span>
            <TypeBadge type={s(post['Type'])} />
            {entryDoor && (
              <MetaChip label="door" value={entryDoor} />
            )}
            {mode && (
              <MetaChip label="mode" value={mode} />
            )}
            {wordCount && (
              <MetaChip label="wc" value={wordCount} />
            )}
            {statusCols.map(col => {
              const val = edits[rowId]?.[col] !== undefined ? edits[rowId][col] : s(post[col])
              return val ? <StatusPill key={col} value={val} /> : null
            })}
          </div>
          <div className="flex items-center gap-2">
            {statusCols.length > 0 && statusCols.slice(0, 1).map(col => (
              <div key={col} className="hidden sm:flex items-center gap-1.5">
                <span className="text-[9px] uppercase tracking-widest" style={{ color: 'var(--text-faint)' }}>
                  {col.replace(/^Status\s*/, '').replace(/[()]/g, '').trim()}
                </span>
                <EditableStatusCell
                  colKey={col} rowId={rowId}
                  original={s(post[col])} edits={edits} onEdit={onEdit}
                />
              </div>
            ))}
            <button
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors hover:bg-[var(--surface-3)]"
              style={{ color: 'var(--text-muted)' }}
              aria-label="Close"
            >
              <X size={16} />
            </button>
          </div>
        </header>

        {/* ─── BODY: PARALLEL TEXT (source ║ final) ───────────────────────── */}
        <div className="grid flex-1 min-h-0 grid-cols-1 lg:grid-cols-[minmax(0,38fr)_minmax(0,62fr)]">

          {/* ──────────── LEFT: SOURCE (static, sticky) ──────────── */}
          <aside
            className="relative flex flex-col overflow-y-auto border-b lg:border-b-0 lg:border-r"
            style={{
              backgroundColor: 'var(--surface-1)',
              borderColor: 'var(--border-2)',
              backgroundImage:
                'radial-gradient(ellipse 80% 50% at 0% 0%, color-mix(in oklab, var(--surface-2) 60%, transparent), transparent)',
            }}
          >
            <div className="sticky top-0 z-10 flex items-center justify-between gap-2 px-7 py-3 backdrop-blur"
                 style={{
                   backgroundColor: 'color-mix(in oklab, var(--surface-1) 92%, transparent)',
                   borderBottom: '1px solid var(--border-2)',
                 }}>
              <div className="flex items-center gap-2">
                <Quote size={11} style={{ color: 'var(--text-muted)' }} />
                <span
                  className="text-[9.5px] font-semibold uppercase tracking-[0.22em]"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Source
                </span>
                <span className="text-[9px]" style={{ color: 'var(--text-faint)' }}>·</span>
                <span className="text-[10px] italic" style={{ color: 'var(--text-faint)' }}>
                  reference (does not change)
                </span>
              </div>
            </div>

            <div className="px-7 py-6 space-y-6">
              {sourceQ ? (
                <article
                  className="text-[15px] leading-[1.72] whitespace-pre-wrap"
                  style={{
                    fontFamily: '"Fraunces", "DM Sans", serif',
                    color: 'var(--text-secondary)',
                    fontFeatureSettings: '"ss01", "ss02"',
                  }}
                >
                  {sourceQ}
                </article>
              ) : (
                <p className="text-[12px] italic" style={{ color: 'var(--text-faint)' }}>
                  No source text captured for this row.
                </p>
              )}

              {/* Source meta — pinned at bottom of left rail */}
              <div className="pt-4 border-t" style={{ borderColor: 'var(--border-2)' }}>
                <div className="grid grid-cols-2 gap-x-3 gap-y-2.5 text-[10.5px]">
                  {mechanic && <MetaRow label="mechanic" value={mechanic} />}
                  {origType && <MetaRow label="closer" value={origType} />}
                  {entryDoor && <MetaRow label="door" value={entryDoor} />}
                  {topic && <MetaRow label="topic" value={topic} colSpan />}
                  {domain && <MetaRow label="domain" value={domain} />}
                  {kind && <MetaRow label="kind" value={kind} />}
                  {score && <MetaRow label="score" value={score} />}
                </div>
              </div>

              {origOpening && (
                <details className="group/o pt-1">
                  <summary className="cursor-pointer select-none list-none flex items-center gap-1.5 text-[9.5px] uppercase tracking-[0.2em] transition-colors"
                           style={{ color: 'var(--text-muted)' }}>
                    <span className="transition-transform group-open/o:rotate-90">›</span>
                    Original opening
                  </summary>
                  <blockquote
                    className="mt-2 border-l-2 pl-3 py-1 text-[12.5px] italic leading-relaxed"
                    style={{
                      borderColor: 'var(--border-1)',
                      color: 'var(--text-secondary)',
                      fontFamily: '"Fraunces", serif',
                    }}
                  >
                    {origOpening}
                  </blockquote>
                </details>
              )}
            </div>
          </aside>

          {/* ──────────── RIGHT: VARIANTS + FINAL ──────────── */}
          <main className="flex flex-col overflow-hidden">
            {/* Variant tab strip */}
            {(variants.length > 0 || finalPost) && (
              <div
                className="shrink-0 border-b px-5 py-3"
                style={{
                  borderColor: 'var(--border-2)',
                  backgroundColor: 'var(--surface-2)',
                }}
              >
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="flex items-center gap-1.5">
                    <VariantTab
                      letter="ORIG"
                      active={active === 'ORIG'}
                      onClick={() => setActive('ORIG')}
                      muted
                    />
                    {variants.map(({ letter }) => (
                      <VariantTab
                        key={letter}
                        letter={letter}
                        active={active === letter}
                        recommended={rec === letter}
                        onClick={() => setActive(letter)}
                      />
                    ))}
                  </div>
                  {activeVariant && active !== 'ORIG' && (onSwapOpener || onSelectVariant) && (
                    <div className="flex items-center gap-2">
                      {onSwapOpener && (
                        <button
                          onClick={() => onSwapOpener(activeVariant.letter, activeVariant.opening, finalPost)}
                          className={clsx(
                            'inline-flex items-center gap-1.5 px-3 py-1.5 text-[10.5px] font-semibold rounded-md transition-all hover:scale-[1.02]',
                            activeAccent?.badge,
                          )}
                        >
                          <ArrowLeftRight size={11} />
                          Use this opener
                        </button>
                      )}
                      {onSelectVariant && (
                        <button
                          onClick={() => onSelectVariant(activeVariant.letter, activeVariant.opening, finalPost)}
                          className="px-2.5 py-1.5 text-[10px] rounded-md transition-colors hover:bg-[var(--surface-3)]"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          Blend ↗
                        </button>
                      )}
                    </div>
                  )}
                </div>

                {/* Tab subtitle */}
                {active !== 'ORIG' && activeVariant && (
                  <div className="mt-2 flex items-center gap-2 flex-wrap">
                    {activeVariant.type && (
                      <span className="text-[10.5px]" style={{ color: 'var(--text-muted)' }}>
                        {activeVariant.type}
                      </span>
                    )}
                    {activeVariant.lift > 0 && <ScoreDots score={activeVariant.lift} />}
                    {rec === activeVariant.letter && (
                      <span
                        className="text-[9px] font-medium rounded-full px-2 py-0.5 inline-flex items-center gap-1"
                        style={{ backgroundColor: 'var(--surface-3)', color: 'var(--text-secondary)' }}
                      >
                        <Sparkles size={9} /> recommended
                      </span>
                    )}
                  </div>
                )}
                {active === 'ORIG' && (
                  <div className="mt-2 text-[10.5px]" style={{ color: 'var(--text-muted)' }}>
                    Final post as shipped — no opener swap applied
                  </div>
                )}
              </div>
            )}

            <div className="flex-1 overflow-y-auto px-7 py-6">

              {/* FINAL POST — the focal column */}
              {displayedBody && (
                <section className="mb-6">
                  <div className="mb-2.5 flex items-baseline justify-between gap-2">
                    <h2
                      className="text-[11px] font-semibold uppercase tracking-[0.22em]"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      Final Post {active !== 'ORIG' && activeVariant && (
                        <span style={{ color: 'var(--text-muted)' }}>
                          · with {activeVariant.letter}
                        </span>
                      )}
                    </h2>
                    {active !== 'ORIG' && (
                      <span className="text-[9.5px] uppercase tracking-widest" style={{ color: 'var(--text-faint)' }}>
                        opener swapped
                      </span>
                    )}
                  </div>
                  <article
                    className="rounded-xl border p-5 whitespace-pre-wrap text-[16.5px] leading-[1.8]"
                    style={{
                      fontFamily: '"Fraunces", "DM Sans", serif',
                      fontFeatureSettings: '"ss01", "ss02"',
                      borderColor: active !== 'ORIG' && activeAccent
                        ? 'color-mix(in oklab, currentColor 20%, var(--border-1))'
                        : 'var(--border-1)',
                      backgroundColor: 'var(--surface-2)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    {/* First line gets a subtle accent if it's a swapped opener */}
                    {active !== 'ORIG' && activeVariant ? (
                      <>
                        <span
                          className={clsx('inline-block px-1 -mx-1 rounded')}
                          style={{
                            backgroundColor: 'color-mix(in oklab, currentColor 8%, transparent)',
                          }}
                        >
                          {activeVariant.opening}
                        </span>
                        {displayedBody.slice(activeVariant.opening.length)}
                      </>
                    ) : (
                      displayedBody
                    )}
                  </article>
                </section>
              )}

              {/* Opener comparison strip — only when a variant is selected */}
              {active !== 'ORIG' && activeVariant && origOpening && (
                <section className="mb-6">
                  <div className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.22em]"
                       style={{ color: 'var(--text-muted)' }}>
                    Opener swap
                  </div>
                  <div className="rounded-xl border overflow-hidden"
                       style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)' }}>
                    <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--border-2)' }}>
                      <div className="text-[9px] uppercase tracking-[0.2em] mb-1.5"
                           style={{ color: 'var(--text-faint)' }}>
                        Was — original
                      </div>
                      <p className="text-[13px] italic leading-relaxed line-through decoration-1"
                         style={{
                           fontFamily: '"Fraunces", serif',
                           color: 'var(--text-faint)',
                           textDecorationColor: 'var(--border-1)',
                         }}>
                        {origOpening}
                      </p>
                    </div>
                    <div className="px-4 py-3">
                      <div className="text-[9px] uppercase tracking-[0.2em] mb-1.5"
                           style={{ color: 'var(--text-muted)' }}>
                        Now — variant {activeVariant.letter}
                      </div>
                      <p className="text-[13.5px] leading-relaxed"
                         style={{
                           fontFamily: '"Fraunces", serif',
                           color: 'var(--text-primary)',
                         }}>
                        {activeVariant.opening}
                      </p>
                      {activeVariant.change && (
                        <p className="mt-2 text-[10.5px] italic" style={{ color: 'var(--text-muted)' }}>
                          {activeVariant.change}
                        </p>
                      )}
                    </div>
                  </div>
                </section>
              )}

              {/* Why this variant wins */}
              {whyText && active !== 'ORIG' && (
                <section className="mb-6">
                  <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.22em]"
                       style={{ color: 'var(--text-muted)' }}>
                    <Sparkles size={11} />
                    Why this opener wins
                  </div>
                  <p
                    className="rounded-xl border-l-2 pl-4 py-2 text-[13px] leading-[1.7] italic"
                    style={{
                      borderColor: activeAccent ? 'currentColor' : 'var(--border-1)',
                      color: 'var(--text-secondary)',
                      fontFamily: '"Fraunces", serif',
                    }}
                  >
                    {whyText}
                  </p>
                </section>
              )}

              {/* Analysis chips — buried gold + weakness + remaining facts */}
              {(buried || weakness) && (
                <section className="mb-6">
                  <div className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.22em]"
                       style={{ color: 'var(--text-muted)' }}>
                    Editor's notes
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    {buried && (
                      <NoteCard label="Buried gold" tone="positive">
                        {buried}
                      </NoteCard>
                    )}
                    {weakness && (
                      <NoteCard label="Weakness" tone="caution">
                        {weakness}
                      </NoteCard>
                    )}
                  </div>
                </section>
              )}

              {/* All fields — collapsed by default */}
              <details className="group/d">
                <summary
                  className="cursor-pointer select-none list-none inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em] transition-colors hover:opacity-80"
                  style={{ color: 'var(--text-faint)' }}
                >
                  <span className="transition-transform group-open/d:rotate-90">›</span>
                  All fields ({headers.length})
                </summary>
                <div className="mt-3 rounded-xl border p-3.5 space-y-1.5"
                     style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)' }}>
                  {headers.map(h => (
                    <div key={h} className="flex gap-3 text-[10.5px]">
                      <span className="font-mono shrink-0 min-w-[140px]" style={{ color: 'var(--text-faint)' }}>
                        {h}
                      </span>
                      <span className="break-words" style={{ color: 'var(--text-secondary)' }}>
                        {s(post[h]) || '—'}
                      </span>
                    </div>
                  ))}
                </div>
              </details>
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}

// ─── Small presentational pieces ──────────────────────────────────────────

function MetaChip({ label, value }: { label: string; value: string }) {
  return (
    <span
      className="inline-flex items-baseline gap-1.5 text-[10px] rounded-md px-2 py-1"
      style={{ backgroundColor: 'var(--surface-3)' }}
    >
      <span className="font-mono uppercase tracking-wider text-[9px]" style={{ color: 'var(--text-faint)' }}>
        {label}
      </span>
      <span className="font-medium" style={{ color: 'var(--text-secondary)' }}>
        {value}
      </span>
    </span>
  )
}

function MetaRow({ label, value, colSpan }: { label: string; value: string; colSpan?: boolean }) {
  return (
    <div className={clsx('flex flex-col gap-0.5', colSpan && 'col-span-2')}>
      <span className="font-mono uppercase tracking-wider text-[8.5px]" style={{ color: 'var(--text-faint)' }}>
        {label}
      </span>
      <span className="leading-snug" style={{ color: 'var(--text-secondary)' }}>
        {value}
      </span>
    </div>
  )
}

function VariantTab({
  letter, active, recommended, onClick, muted,
}: {
  letter: string
  active: boolean
  recommended?: boolean
  onClick: () => void
  muted?: boolean
}) {
  const isOrig = letter === 'ORIG'
  return (
    <button
      onClick={onClick}
      className={clsx(
        'relative inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 font-mono text-[10.5px] font-medium uppercase tracking-wider transition-all',
        active
          ? 'bg-[var(--surface-1)] shadow-sm'
          : 'hover:bg-[var(--surface-1)]/40',
      )}
      style={{
        color: active
          ? 'var(--text-primary)'
          : muted ? 'var(--text-faint)' : 'var(--text-muted)',
        boxShadow: active ? '0 1px 0 0 var(--border-1) inset' : undefined,
      }}
    >
      {isOrig ? 'orig' : letter}
      {recommended && (
        <span
          className="h-1 w-1 rounded-full"
          style={{ backgroundColor: active ? 'var(--text-primary)' : 'var(--text-muted)' }}
        />
      )}
      {active && (
        <span
          className="absolute -bottom-[3px] left-1/2 -translate-x-1/2 h-[2px] w-[80%] rounded-full"
          style={{
            backgroundColor: 'var(--text-primary)',
          }}
        />
      )}
    </button>
  )
}

function NoteCard({ label, children, tone }: { label: string; children: React.ReactNode; tone: 'positive' | 'caution' }) {
  const accent = tone === 'positive'
    ? 'color-mix(in oklab, gold 30%, var(--border-1))'
    : 'color-mix(in oklab, tomato 30%, var(--border-1))'
  return (
    <div
      className="rounded-xl border-l-2 pl-3 pr-3.5 py-2.5"
      style={{
        borderLeftColor: accent,
        backgroundColor: 'var(--surface-2)',
        borderTop: '1px solid var(--border-2)',
        borderRight: '1px solid var(--border-2)',
        borderBottom: '1px solid var(--border-2)',
        borderTopLeftRadius: 4,
        borderBottomLeftRadius: 4,
      }}
    >
      <div
        className="text-[8.5px] font-semibold uppercase tracking-[0.22em] mb-1"
        style={{ color: 'var(--text-faint)' }}
      >
        {label}
      </div>
      <div className="text-[12.5px] leading-[1.65] italic"
           style={{
             fontFamily: '"Fraunces", serif',
             color: 'var(--text-secondary)',
           }}>
        {children}
      </div>
    </div>
  )
}
