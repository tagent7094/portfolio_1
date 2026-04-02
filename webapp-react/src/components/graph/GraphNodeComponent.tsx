import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import clsx from 'clsx'

const TYPE_COLORS: Record<string, string> = {
  founder: 'bg-gray-200',
  category: 'bg-gray-500',
  belief: 'bg-purple-500',
  story: 'bg-blue-500',
  style_rule: 'bg-amber-500',
  thinking_model: 'bg-emerald-500',
  contrast_pair: 'bg-pink-500',
  vocabulary: 'bg-red-500',
}

const TYPE_RING: Record<string, string> = {
  founder: 'ring-gray-400',
  category: 'ring-gray-600',
}

function GraphNodeComponent({ data }: NodeProps) {
  const nodeType = (data.nodeType as string) || 'default'
  const isHub = nodeType === 'founder' || nodeType === 'category'
  const colorClass = TYPE_COLORS[nodeType] || 'bg-gray-600'
  const hasChildren = data.hasChildren as boolean
  const childCount = data.childCount as number
  const isExpanded = data.isExpanded as boolean

  return (
    <div className="flex flex-col items-center gap-0.5 cursor-pointer group">
      <Handle type="target" position={Position.Top} className="!bg-transparent !border-0 !w-1 !h-1" />

      <div className="relative">
        <div
          className={clsx(
            'rounded-full shadow-lg transition-transform group-hover:scale-110',
            colorClass,
            isHub ? 'h-12 w-12 ring-2' : 'h-5 w-5',
            isHub && (TYPE_RING[nodeType] || 'ring-gray-600'),
            isExpanded && isHub && 'ring-indigo-500',
          )}
        />

        {/* Child count badge */}
        {hasChildren && childCount > 0 && (
          <div className={clsx(
            'absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full text-[8px] font-bold',
            isExpanded ? 'bg-indigo-500 text-white' : 'bg-gray-700 text-gray-300',
          )}>
            {childCount > 99 ? '99+' : childCount}
          </div>
        )}

        {/* Expand indicator */}
        {hasChildren && isHub && (
          <div className="absolute -bottom-0.5 left-1/2 -translate-x-1/2 text-[8px] text-gray-400">
            {isExpanded ? '▼' : '▶'}
          </div>
        )}
      </div>

      <span
        className={clsx(
          'max-w-[100px] truncate text-center leading-tight',
          isHub ? 'text-[11px] font-semibold text-gray-200' : 'text-[9px] text-gray-400',
        )}
        title={data.label as string}
      >
        {data.label as string}
      </span>

      <Handle type="source" position={Position.Bottom} className="!bg-transparent !border-0 !w-1 !h-1" />
    </div>
  )
}

export default memo(GraphNodeComponent)
