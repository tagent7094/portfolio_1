import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import clsx from 'clsx'

/* ─── Color system matching the D3 HTML knowledge graph ─── */

const TYPE_STYLES: Record<string, { bg: string; ring: string; glow: string }> = {
  founder: { bg: 'bg-indigo-200', ring: 'ring-indigo-400', glow: 'shadow-indigo-500/20' },
  category: { bg: 'bg-slate-400', ring: 'ring-slate-500', glow: 'shadow-slate-500/10' },
  belief: { bg: 'bg-violet-400', ring: 'ring-violet-500', glow: 'shadow-violet-500/20' },
  story: { bg: 'bg-blue-400', ring: 'ring-blue-500', glow: 'shadow-blue-500/20' },
  style_rule: { bg: 'bg-amber-400', ring: 'ring-amber-500', glow: 'shadow-amber-500/20' },
  thinking_model: { bg: 'bg-emerald-400', ring: 'ring-emerald-500', glow: 'shadow-emerald-500/20' },
  contrast_pair: { bg: 'bg-pink-400', ring: 'ring-pink-500', glow: 'shadow-pink-500/20' },
  vocabulary: { bg: 'bg-red-400', ring: 'ring-red-500', glow: 'shadow-red-500/20' },
  viral_brain: { bg: 'bg-amber-300', ring: 'ring-amber-500', glow: 'shadow-amber-500/25' },
  hook_type: { bg: 'bg-orange-400', ring: 'ring-orange-500', glow: 'shadow-orange-500/20' },
  structure_template: { bg: 'bg-cyan-400', ring: 'ring-cyan-500', glow: 'shadow-cyan-500/20' },
  viral_pattern: { bg: 'bg-purple-400', ring: 'ring-purple-500', glow: 'shadow-purple-500/20' },
  engagement_profile: { bg: 'bg-green-400', ring: 'ring-green-500', glow: 'shadow-green-500/20' },
  writing_technique: { bg: 'bg-rose-400', ring: 'ring-rose-500', glow: 'shadow-rose-500/20' },
}

const TYPE_TEXT_COLORS: Record<string, string> = {
  founder: 'text-indigo-900',
  category: 'text-slate-900',
  belief: 'text-violet-950',
  story: 'text-blue-950',
  style_rule: 'text-amber-950',
  thinking_model: 'text-emerald-950',
  contrast_pair: 'text-pink-950',
  vocabulary: 'text-red-950',
  viral_brain: 'text-amber-950',
  hook_type: 'text-orange-950',
  structure_template: 'text-cyan-950',
  viral_pattern: 'text-purple-950',
  engagement_profile: 'text-green-950',
  writing_technique: 'text-rose-950',
}

/**
 * Graph node for @xyflow/react usage.
 * Mirrors the D3 HTML visual style: circle nodes with hover glow,
 * size-based importance, group-colored fills.
 */
function GraphNodeComponent({ data }: NodeProps<Record<string, unknown>>) {
  const nodeType = (data.nodeType as string) || 'category'
  const isHub = nodeType === 'founder' || nodeType === 'category' || nodeType === 'viral_brain'
  const style = TYPE_STYLES[nodeType] || TYPE_STYLES.category
  const textColor = TYPE_TEXT_COLORS[nodeType] || 'text-slate-900'
  const label = data.label as string
  const isConnected = data.isConnected as boolean | undefined
  const isHighlightDimmed = data.isDimmed as boolean | undefined

  return (
    <div
      className={clsx(
        'flex flex-col items-center gap-1 cursor-pointer group transition-opacity duration-200',
        isHighlightDimmed && 'opacity-[0.08]',
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0 !w-0.5 !h-0.5" />

      <div className="relative">
        {/* Main circle */}
        <div
          className={clsx(
            'rounded-full transition-all duration-200',
            'group-hover:scale-[1.3] group-hover:shadow-lg',
            style.bg,
            style.glow,
            isHub ? 'h-14 w-14 ring-2 shadow-lg' : 'h-6 w-6 shadow-md',
            isHub && style.ring,
            // White stroke on hover (matching D3 HTML .node:hover circle)
            !isHub && 'group-hover:ring-2 group-hover:ring-white',
          )}
        >
          {/* Inner label for hubs */}
          {isHub && (
            <div className={clsx(
              'absolute inset-0 flex items-center justify-center',
              'text-[9px] font-bold leading-none text-center px-1',
              textColor,
            )}>
              {label.length > 8 ? label.slice(0, 7) + '…' : label}
            </div>
          )}
        </div>

        {/* Selection / highlight glow */}
        {data.isSelected && (
          <div className="absolute inset-[-4px] rounded-full ring-2 ring-indigo-500/50 animate-pulse" />
        )}
        {isConnected && !isHighlightDimmed && (
          <div className="absolute inset-[-3px] rounded-full ring-1 ring-purple-500/40" />
        )}
      </div>

      {/* Label below */}
      <span
        className={clsx(
          'max-w-[110px] truncate text-center leading-tight transition-all duration-200',
          isHub
            ? 'text-[11px] font-semibold text-slate-200 mt-0.5'
            : 'text-[9px] text-[#aaa] group-hover:text-white group-hover:text-sm',
        )}
        title={label}
      >
        {label}
      </span>

      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0 !w-0.5 !h-0.5" />
    </div>
  )
}

export default memo(GraphNodeComponent)