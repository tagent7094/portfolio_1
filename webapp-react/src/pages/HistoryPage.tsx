import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, ChevronDown, ChevronUp } from 'lucide-react'
import { apiGet } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'

interface OutputFile {
  name: string
  size: number
  content?: string
}

export default function HistoryPage() {
  const active = useFounderStore((s) => s.active)
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data: outputsData } = useQuery<{ outputs: OutputFile[] }>({
    queryKey: ['outputs', active],
    queryFn: () => apiGet('/api/outputs'),
  })
  const outputs = outputsData?.outputs ?? []

  const toggle = (filename: string) => {
    setExpanded((prev) => (prev === filename ? null : filename))
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    return `${(bytes / 1024).toFixed(1)} KB`
  }

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">History</h2>

      {outputs.length === 0 && (
        <p className="py-8 text-center text-gray-400">
          No generated posts yet.
        </p>
      )}

      <div className="space-y-2">
        {outputs.map((file) => (
          <div
            key={file.name}
            className="rounded-xl border border-gray-800 bg-gray-900"
          >
            <button
              onClick={() => toggle(file.name)}
              className="flex w-full items-center justify-between px-4 py-3 text-left"
            >
              <div className="flex items-center gap-3">
                <FileText size={16} className="text-gray-400" />
                <span className="text-sm font-medium text-gray-100">
                  {file.name}
                </span>
                <span className="text-xs text-gray-500">
                  {formatSize(file.size)}
                </span>
              </div>
              {expanded === file.name ? (
                <ChevronUp size={16} className="text-gray-400" />
              ) : (
                <ChevronDown size={16} className="text-gray-400" />
              )}
            </button>
            {expanded === file.name && file.content && (
              <div className="border-t border-gray-800 px-4 py-3">
                <pre className="whitespace-pre-wrap text-sm leading-relaxed text-gray-300">
                  {file.content}
                </pre>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
