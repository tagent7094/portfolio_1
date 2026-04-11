import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import clsx from 'clsx'

interface GraphNodeData extends Record<string, unknown> {
  nodeType?: string
  group?: string
  label?: string
  size?: number
  isConnected?: boolean
  isDimmed?: boolean
  isHovered?: boolean
  isHit?: boolean
  zoomLevel?: number
}

/* ─── Color system EXACT match to D3 HTML knowledge graph ─── */
const TYPE_STYLES: Record<string, { bg: string; ring: string; glow: string; fill: string }> = {
  // D3 HTML groups
  purple: { bg: 'bg-[#9d50bb]', ring: 'ring-[#9d50bb]', glow: 'shadow-[#9d50bb]/30', fill: '#9d50bb' },
  green: { bg: 'bg-[#2ecc71]', ring: 'ring-[#2ecc71]', glow: 'shadow-[#2ecc71]/30', fill: '#2ecc71' },
  red: { bg: 'bg-[#e74c3c]', ring: 'ring-[#e74c3c]', glow: 'shadow-[#e74c3c]/30', fill: '#e74c3c' },
  default: { bg: 'bg-[#888]', ring: 'ring-[#666]', glow: 'shadow-[#888]/20', fill: '#888' },

  // Extended types mapped to D3 groups
  founder: { bg: 'bg-[#9d50bb]', ring: 'ring-[#9d50bb]', glow: 'shadow-[#9d50bb]/40', fill: '#9d50bb' },
  category: { bg: 'bg-[#9d50bb]', ring: 'ring-[#9d50bb]', glow: 'shadow-[#9d50bb]/30', fill: '#9d50bb' },
  belief: { bg: 'bg-[#2ecc71]', ring: 'ring-[#2ecc71]', glow: 'shadow-[#2ecc71]/30', fill: '#2ecc71' },
  story: { bg: 'bg-[#e74c3c]', ring: 'ring-[#e74c3c]', glow: 'shadow-[#e74c3c]/30', fill: '#e74c3c' },
  style_rule: { bg: 'bg-[#888]', ring: 'ring-[#666]', glow: 'shadow-[#888]/20', fill: '#888' },
  thinking_model: { bg: 'bg-[#888]', ring: 'ring-[#666]', glow: 'shadow-[#888]/20', fill: '#888' },
  contrast_pair: { bg: 'bg-[#888]', ring: 'ring-[#666]', glow: 'shadow-[#888]/20', fill: '#888' },
  vocabulary: { bg: 'bg-[#888]', ring: 'ring-[#666]', glow: 'shadow-[#888]/20', fill: '#888' },
  viral_brain: { bg: 'bg-[#9d50bb]', ring: 'ring-[#9d50bb]', glow: 'shadow-[#9d50bb]/40', fill: '#9d50bb' },
  hook_type: { bg: 'bg-[#888]', ring: 'ring-[#666]', glow: 'shadow-[#888]/20', fill: '#888' },
  structure_template: { bg: 'bg-[#888]', ring: 'ring-[#666]', glow: 'shadow-[#888]/20', fill: '#888' },
  viral_pattern: { bg: 'bg-[#888]', ring: 'ring-[#666]', glow: 'shadow-[#888]/20', fill: '#888' },
  engagement_profile: { bg: 'bg-[#888]', ring: 'ring-[#666]', glow: 'shadow-[#888]/20', fill: '#888' },
  writing_technique: { bg: 'bg-[#888]', ring: 'ring-[#666]', glow: 'shadow-[#888]/20', fill: '#888' },
}

const BASE_SIZE: Record<string, number> = {
  founder: 56, category: 40, belief: 32, story: 24, style_rule: 20,
  thinking_model: 20, contrast_pair: 20, vocabulary: 20,
  viral_brain: 56, hook_type: 24, structure_template: 20,
  viral_pattern: 20, engagement_profile: 24, writing_technique: 20,
  // D3 HTML size mapping
  purple: 40, green: 32, red: 24, default: 20,
}

/**
 * Graph node for @xyflow/react usage.
 * Mirrors the D3 HTML visual style: circle nodes with hover glow,
 * size-based importance, group-colored fills, and adaptive labels.
 */
function GraphNodeComponent({ data, selected }: NodeProps) {
  const d = data as GraphNodeData
  const nodeType = (d.nodeType as string) || (d.group as string) || 'default'
  const isHub = nodeType === 'founder' || nodeType === 'category' || nodeType === 'viral_brain' || nodeType === 'purple'

  const style = TYPE_STYLES[nodeType] || TYPE_STYLES.default
  const baseSize = BASE_SIZE[nodeType] || BASE_SIZE.default

  // Size scaling based on D3 HTML size prop
  const d3Size = d.size || 1
  const scaledSize = Math.round(baseSize * (d3Size / 10))

  const label = d.label || ''
  const isConnected = d.isConnected
  const isHighlightDimmed = d.isDimmed
  const zoomLevel = d.zoomLevel || 1

  // Zoom-adaptive label visibility (matching D3 HTML updateLabelVisibility)
  const shouldShowLabel = (() => {
    if (isHighlightDimmed) return false
    if (selected || d.isHovered) return true
    if (isHub) return zoomLevel > 0.4
    return zoomLevel > 0.8
  })()

  return (
    <div
      className={clsx(
        'flex flex-col items-center gap-1.5 cursor-grab active:cursor-grabbing group transition-all duration-200',
        isHighlightDimmed && 'opacity-[0.08]',
        'select-none'
      )}

    >
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-transparent !border-0 !w-1 !h-1 !opacity-0"
      />

      <div className="relative">
        {/* Main circle with D3 HTML styling */}
        <div
          className={clsx(
            'rounded-full transition-all duration-200 ease-out',
            'group-hover:scale-[1.3] group-hover:shadow-xl',
            style.bg,
            style.glow,
            // Size classes
            isHub ? 'ring-2 shadow-lg' : 'shadow-md',
            // White stroke on hover (matching D3 HTML .node:hover circle)
            !isHub && 'group-hover:ring-2 group-hover:ring-white/80',
            // Selection ring
            selected && 'ring-2 ring-[#6366f1]'
          )}
          style={{
            width: scaledSize,
            height: scaledSize,
            // Custom glow for hubs/selected/hovered
            boxShadow: (selected || d.isHovered || isHub) && !isHighlightDimmed
              ? `0 0 ${isHub ? 25 : 20}px ${style.glow.replace('shadow-', '').replace('/30', '').replace('/40', '')}`
              : undefined
          }}
        >
          {/* Inner label for hubs (centered text like D3 HTML) */}
          {isHub && (
            <div className={clsx(
              'absolute inset-0 flex items-center justify-center',
              'text-[9px] font-bold leading-none text-center px-1',
              'text-[#1a1a1a]'
            )}>
              {label.length > 10 ? label.slice(0, 9) + '…' : label}
            </div>
          )}
        </div>

        {/* Connected highlight ring (purple glow like D3 HTML) */}
        {isConnected && !isHighlightDimmed && (
          <div
            className="absolute inset-[-4px] rounded-full ring-1 ring-[#9d50bb]/40 pointer-events-none"
            style={{ animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' }}
          />
        )}

        {/* Selection pulse animation */}
        {selected && (
          <div className="absolute inset-[-6px] rounded-full ring-2 ring-[#6366f1]/50 animate-pulse pointer-events-none" />
        )}
      </div>

      {/* Label below node (zoom-adaptive like D3 HTML) */}
      {shouldShowLabel && !isHub && (
        <span
          className={clsx(
            'max-w-[120px] truncate text-center leading-tight transition-all duration-200',
            'text-[9px] group-hover:text-white',
            d.isHit ? 'text-[#fbbf24] font-medium' : 'text-[#aaaaaa]',
            selected && 'text-white font-medium',
            d.isHovered && 'text-white text-[10px]'
          )}
          style={{
            fontSize: shouldShowLabel ? `${Math.max(9, 10 / zoomLevel)}px` : '9px',
            opacity: isHighlightDimmed ? 0 : (isHub ? 1 : 0.7),
          }}
          title={label}
        >
          {label.length > 22 ? label.slice(0, 21) + '…' : label}
        </span>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-transparent !border-0 !w-1 !h-1 !opacity-0"
      />
    </div>
  )
}

export default memo(GraphNodeComponent)