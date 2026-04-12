import { useState } from 'react'
import { ChevronDown, ChevronUp, Cpu } from 'lucide-react'
import type { PostVariant } from '../../types/api'

interface Props {
  post: PostVariant
  streamingText?: string
}

export default function PostCard({ post, streamingText }: Props) {
  const [expanded, setExpanded] = useState(false)
  const displayText = streamingText ?? post.text
  let content = displayText
  let reasoning = null
  const regex = /<reasoning>([\s\S]*?)<\/reasoning>/i
  const match = content.match(regex)
  if (match) {
    reasoning = match[1].trim()
    content = content.replace(regex, '').trim()
  } else if (content.includes('<reasoning>')) {
    const parts = content.split('<reasoning>')
    content = parts[0].trim()
    reasoning = parts[1].trim()
  }

  const charCount = content.length
  const isLong = charCount > 200

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5 rounded-full bg-gray-800 px-2.5 py-0.5 text-xs font-medium text-white">
          <Cpu size={12} />
          {post.engine_name || post.engine_id}
        </span>
        <span className="text-xs text-gray-500">{charCount} chars</span>
      </div>

      {reasoning && (
        <div className="mb-3 rounded border border-white/50 bg-white/20 p-2.5 text-xs text-white">
          <span className="font-semibold text-white block mb-1 uppercase tracking-wider">Reasoning</span>
          <span className="italic opacity-80">{reasoning}</span>
        </div>
      )}

      <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-200">
        {expanded || !isLong ? content : content.slice(0, 200) + '...'}
        {streamingText !== undefined && (
          <span className="inline-block h-4 w-0.5 animate-pulse bg-indigo-400 ml-0.5" />
        )}
      </p>

      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 flex items-center gap-1 text-xs text-white hover:text-white"
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  )
}
