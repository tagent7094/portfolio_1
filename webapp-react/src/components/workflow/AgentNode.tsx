import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Bot, Database, FileOutput } from 'lucide-react'
import clsx from 'clsx'

const STATUS_STYLES: Record<string, string> = {
  idle: 'bg-gray-600',
  running: 'bg-indigo-500 animate-pulse',
  done: 'bg-green-500',
  error: 'bg-red-500',
}

const TYPE_ICONS: Record<string, typeof Bot> = {
  agent: Bot,
  source: Database,
  output: FileOutput,
}

function AgentNode({ data }: NodeProps) {
  const status = (data.status as string) || 'idle'
  const nodeKind = (data.nodeKind as string) || 'agent'
  const Icon = TYPE_ICONS[nodeKind] || Bot

  return (
    <div className="min-w-[140px] rounded-xl border border-gray-700 bg-gray-900 px-4 py-3 shadow-lg">
      <Handle type="target" position={Position.Top} className="!bg-gray-600 !border-gray-500" />

      <div className="flex items-center gap-2">
        <Icon size={16} className="text-gray-400" />
        <span className="text-sm font-medium text-gray-100">
          {data.label as string}
        </span>
        <div
          className={clsx(
            'ml-auto h-2.5 w-2.5 rounded-full',
            STATUS_STYLES[status],
          )}
        />
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-gray-600 !border-gray-500" />
    </div>
  )
}

export default memo(AgentNode)
