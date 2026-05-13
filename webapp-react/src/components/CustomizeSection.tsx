import { X, ChevronRight, BookOpen } from 'lucide-react'
import clsx from 'clsx'
import { VARIANT_LETTERS, VARIANT_ACCENT } from './pack-table/types'
import { s } from './pack-table/helpers'
import { VariantBadge, ScoreDots } from './pack-table/cells'

interface Props {
  post: Record<string, any>
  onSelectVariant: (letter: string, opener: string, body: string) => void
  onSwapOpener: (letter: string, opener: string, body: string) => void
  onShowDetails: () => void
  onClose: () => void
}

export default function CustomizeSection({ post, onSelectVariant, onSwapOpener, onShowDetails, onClose }: Props) {
  const finalPost = s(post['Finalized Post'] || post['Final Post'])
  const rec = s(post['Recommended']).trim().toUpperCase()

  const variants = VARIANT_LETTERS.map(v => ({
    letter: v as string,
    opening: s(post[`${v}, Opening`] ?? post[`${v} - Opening`]),
    type: s(post[`${v}, Rewrite Type`] ?? post[`${v} - Rewrite Type`]),
    change: s(post[`${v}, Key Change`] ?? post[`${v} - Key Change`]),
    lift: Number(post[`${v}, Expected Lift`] ?? post[`${v} - Expected Lift`]) || 0,
  })).filter(v => v.opening)

  if (variants.length === 0) return null

  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-1)' }}>
      <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: 'var(--border-2)' }}>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px]" style={{ color: 'var(--text-faint)' }}>#{s(post['Row #'])}</span>
          <span className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>
            Select an opener to customize
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onShowDetails}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] transition-colors hover:opacity-80"
            style={{ color: 'var(--text-muted)', backgroundColor: 'var(--surface-2)', border: '1px solid var(--border-1)' }}
          >
            Full Details <ChevronRight size={11} />
          </button>
          <button onClick={onClose} className="transition-opacity hover:opacity-70" style={{ color: 'var(--text-muted)' }}>
            <X size={15} />
          </button>
        </div>
      </div>

      {finalPost && (
        <div className="px-5 py-3 border-b" style={{ borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)' }}>
          <div className="flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-widest mb-1.5" style={{ color: 'var(--text-faint)' }}>
            <BookOpen size={10} /> Finalized Post
          </div>
          <p className="text-[12px] leading-relaxed line-clamp-3" style={{ color: 'var(--text-secondary)' }}>
            {finalPost}
          </p>
        </div>
      )}

      <div className="p-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          {variants.map(({ letter, opening, type, change, lift }) => {
            const isRec = rec === letter
            const accent = VARIANT_ACCENT[letter]
            return (
              <div
                key={letter}
                className={clsx(
                  'text-left rounded-xl border p-4 transition-all group',
                  isRec ? `${accent.cell} border-white/20 ring-1 ring-white/10` : '',
                )}
                style={!isRec ? { borderColor: 'var(--border-2)', backgroundColor: 'var(--surface-2)' } : {}}
              >
                <div className="flex items-center gap-2 mb-2.5">
                  <VariantBadge letter={letter} />
                  {type && <span className="text-[10px] truncate" style={{ color: 'var(--text-muted)' }}>{type}</span>}
                  {isRec && (
                    <span className="text-[8px] font-semibold rounded-full px-1.5 py-0.5 ml-auto shrink-0"
                      style={{ backgroundColor: 'var(--surface-3)', color: 'var(--text-secondary)' }}>
                      REC
                    </span>
                  )}
                </div>
                <p className="text-[12px] leading-snug line-clamp-4" style={{ color: isRec ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                  {opening}
                </p>
                {change && (
                  <p className="mt-2 text-[10px] italic line-clamp-2" style={{ color: 'var(--text-muted)' }}>{change}</p>
                )}
                {lift > 0 && (
                  <div className="mt-2">
                    <ScoreDots score={lift} />
                  </div>
                )}
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => onSwapOpener(letter, opening, finalPost)}
                    className="flex-1 text-center text-[10px] font-medium rounded-md py-1.5 transition-colors hover:opacity-80 cursor-pointer"
                    style={{ backgroundColor: 'var(--surface-3)', color: 'var(--text-secondary)', border: '1px solid var(--border-1)' }}
                  >
                    Use This Opener
                  </button>
                  <button
                    onClick={() => onSelectVariant(letter, opening, finalPost)}
                    className="text-[9px] px-2 py-1.5 rounded-md transition-colors hover:opacity-80 cursor-pointer"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    Blend ↗
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
