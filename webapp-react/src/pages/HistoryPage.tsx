import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, ChevronRight, Clock } from 'lucide-react'
import clsx from 'clsx'
import { apiGet } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import { PageHeader, Card, Spinner, EmptyState } from '../components/ui'

interface OutputFile { name: string; size: number; content?: string }

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

function formatDate(name: string) {
  const match = name.match(/(\d{4}-\d{2}-\d{2})/)
  if (!match) return null
  const d = new Date(match[1])
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function HistoryPage() {
  const active = useFounderStore((s) => s.active)
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data, isLoading } = useQuery<{ outputs: OutputFile[] }>({
    queryKey: ['outputs', active],
    queryFn: () => apiGet('/api/outputs'),
  })
  const outputs = data?.outputs ?? []

  if (isLoading) return <Spinner fullPage />

  return (
    <div className="space-y-6">
      <PageHeader
        title="History"
        subtitle={`${outputs.length} generated file${outputs.length !== 1 ? 's' : ''}`}
      />

      {outputs.length === 0 ? (
        <EmptyState
          icon={<Clock size={22} />}
          title="No history yet"
          description="Generated posts will appear here after your first content run."
        />
      ) : (
        <div className="space-y-2">
          {outputs.map((file) => {
            const isOpen = expanded === file.name
            const date = formatDate(file.name)
            return (
              <Card
                key={file.name}
                className={clsx('overflow-hidden transition-all duration-150', isOpen && 'ring-1 ring-[var(--border-3)]')}
              >
                <button
                  onClick={() => setExpanded(isOpen ? null : file.name)}
                  className="flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:bg-[var(--surface-3)]"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-3)]">
                      <FileText size={16} className="text-[var(--text-muted)]" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-[13.5px] font-medium text-[var(--text-primary)]">{file.name}</p>
                      <p className="mt-0.5 text-[11.5px] text-[var(--text-muted)]">
                        {date && <span>{date} · </span>}
                        {formatSize(file.size)}
                      </p>
                    </div>
                  </div>
                  <ChevronRight
                    size={16}
                    className={clsx(
                      'shrink-0 text-[var(--text-muted)] transition-transform duration-200',
                      isOpen && 'rotate-90',
                    )}
                  />
                </button>

                {isOpen && file.content && (
                  <div className="border-t border-[var(--border-2)] px-5 py-4">
                    <pre className="whitespace-pre-wrap font-[var(--font-mono)] text-[12.5px] leading-relaxed text-[var(--text-secondary)]">
                      {file.content}
                    </pre>
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
