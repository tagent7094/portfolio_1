import { useState, useRef, useEffect } from 'react'
import { Play, Loader2, Square, FileSpreadsheet, CheckCircle2, Eye } from 'lucide-react'
import { streamSSE, apiGet } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import { PageHeader, Card, CardBody, Button } from '../components/ui'
import TraceViewer from '../components/TraceViewer'

interface LogEntry { stage: string; status: string; ts: number }

export default function GeneratePage() {
  const active = useFounderStore((s) => s.active)

  const [nSources, setNSources] = useState(3)
  const [creativity, setCreativity] = useState(0.5)
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('')
  const [log, setLog] = useState<LogEntry[]>([])
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [showTraces, setShowTraces] = useState(false)
  const [traceData, setTraceData] = useState<any>(null)
  const [loadingTraces, setLoadingTraces] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)
  const lastPackDateRef = useRef<string>('')

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log.length])

  const handleGenerate = async () => {
    if (!active) {
      setError('No founder selected')
      return
    }
    setGenerating(true)
    setProgress(0)
    setStage('connecting...')
    setLog([])
    setDone(false)
    setError('')
    setTraceData(null)
    setShowTraces(false)

    const abort = new AbortController()
    abortRef.current = abort

    try {
      await streamSSE(
        '/api/generate/batch/stream',
        { founder_slug: active, n_sources: nSources, creativity, platform: 'linkedin' },
        (event) => {
          setProgress(event.progress || 0)
          setStage(event.stage)
          setLog(prev => [...prev, { stage: event.stage, status: event.status, ts: Date.now() }])
          if (event.data?.filepath) {
            const match = event.data.filepath.match(/(\d{4}-\d{2}-\d{2})/)
            if (match) lastPackDateRef.current = match[1]
          }
          if (event.data?.error) {
            setError(event.data.error)
          }
          if (event.status === 'pipeline_done') {
            setDone(true)
            setGenerating(false)
          }
        },
        abort.signal,
      )
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        setError(e?.message || 'Generation failed')
      }
    } finally {
      setGenerating(false)
      abortRef.current = null
    }
  }

  const handleCancel = () => {
    abortRef.current?.abort()
    setGenerating(false)
  }

  const loadTraces = async () => {
    if (!lastPackDateRef.current || !active) return
    setLoadingTraces(true)
    try {
      const data = await apiGet<any>(`/api/admin/founders/${active}/post-packs/${lastPackDateRef.current}/traces`)
      setTraceData(data)
      setShowTraces(true)
    } catch {
      setShowTraces(true)
    } finally {
      setLoadingTraces(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Generate Posts"
        subtitle={`Batch cowork engine — ${nSources * 9} posts from ${nSources} source${nSources !== 1 ? 's' : ''}`}
      />

      <div className="grid gap-5 lg:grid-cols-[340px_1fr]">
        {/* Config panel */}
        <Card>
          <CardBody className="space-y-5">
            <div>
              <label className="mb-2 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Founder
              </label>
              <div className="rounded-lg border border-[var(--border-1)] bg-[var(--surface-3)] px-3 py-2 text-[13px] text-[var(--text-primary)]">
                {active}
              </div>
            </div>

            <div>
              <label className="mb-2 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Source Posts ({nSources})
              </label>
              <input
                type="range" min={1} max={10} value={nSources}
                onChange={e => setNSources(Number(e.target.value))}
                disabled={generating}
                className="w-full accent-[var(--text-primary)]"
              />
              <div className="mt-1 flex justify-between text-[10px] text-[var(--text-faint)]">
                <span>1</span><span>5</span><span>10</span>
              </div>
              <p className="mt-1.5 text-[11px] text-[var(--text-muted)]">
                Each source generates 9 posts (3 mirrored + 6 mechanics)
              </p>
            </div>

            <div>
              <label className="mb-2 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Creativity ({creativity.toFixed(1)})
              </label>
              <input
                type="range" min={0} max={1} step={0.1} value={creativity}
                onChange={e => setCreativity(Number(e.target.value))}
                disabled={generating}
                className="w-full accent-[var(--text-primary)]"
              />
              <div className="mt-1 flex justify-between text-[10px] text-[var(--text-faint)]">
                <span>Conservative</span><span>Balanced</span><span>Creative</span>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] p-3 text-[12px] text-[var(--text-muted)]">
              <p className="font-semibold text-[var(--text-secondary)]">{nSources * 9} posts total</p>
              <p className="mt-0.5">{nSources} source{nSources !== 1 ? 's' : ''} × 9 per source</p>
              <p className="mt-0.5">5-gate amplifier + convergence test</p>
              <p className="mt-0.5">Web search enrichment + full traceability</p>
            </div>

            {/* Pipeline steps */}
            <div className="space-y-1">
              <div className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)] mb-1.5">Pipeline</div>
              {[
                'Deep founder internalization (9 dimensions)',
                'Voice calibration check',
                'Web search for trending topics & facts',
                'Source post selection & ranking',
                `Pack generation (${nSources}× — 9 posts each)`,
                '5-gate opening line amplifier',
                'Convergence test per pack',
              ].map((step, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px] text-[var(--text-muted)]">
                  <span className="shrink-0 mt-0.5 text-[9px] font-mono text-[var(--text-faint)]">{i + 1}.</span>
                  {step}
                </div>
              ))}
            </div>

            {!generating && !done && (
              <Button
                variant="primary"
                className="w-full"
                onClick={handleGenerate}
                icon={<Play size={14} />}
              >
                Start Generation
              </Button>
            )}

            {generating && (
              <Button
                variant="secondary"
                className="w-full"
                onClick={handleCancel}
                icon={<Square size={14} />}
              >
                Cancel
              </Button>
            )}

            {done && (
              <div className="space-y-2">
                <div className="flex items-center gap-2 rounded-lg bg-[var(--success-dim)] px-3 py-2 text-[12px] text-[var(--success)]">
                  <CheckCircle2 size={14} />
                  Pack generated successfully
                </div>
                <Button
                  variant="secondary"
                  className="w-full"
                  onClick={loadTraces}
                  loading={loadingTraces}
                  icon={<Eye size={14} />}
                >
                  View Full Traceability
                </Button>
                <Button
                  variant="primary"
                  className="w-full"
                  onClick={() => { setDone(false); setTraceData(null); setShowTraces(false) }}
                  icon={<Play size={14} />}
                >
                  Generate Another
                </Button>
              </div>
            )}

            {error && (
              <div className="rounded-lg bg-[var(--error-dim)] px-3 py-2 text-[12px] text-[var(--error)]">
                {error}
              </div>
            )}
          </CardBody>
        </Card>

        {/* Progress + log + traces */}
        <div className="space-y-5">
          <Card>
            <CardBody>
              {!generating && log.length === 0 && !done && !showTraces && (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <FileSpreadsheet size={32} className="mb-3 text-[var(--text-faint)]" />
                  <p className="text-[13px] text-[var(--text-muted)]">
                    Configure and start generation to see progress here
                  </p>
                  <p className="mt-2 text-[11px] text-[var(--text-faint)]">
                    Every LLM call, web search, and decision will be traced
                  </p>
                </div>
              )}

              {(generating || log.length > 0) && (
                <div className="space-y-4">
                  {/* Progress bar */}
                  <div>
                    <div className="mb-1.5 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {generating && <Loader2 size={12} className="animate-spin text-[var(--text-primary)]" />}
                        {done && <CheckCircle2 size={12} className="text-[var(--success)]" />}
                        <span className="text-[12px] font-medium text-[var(--text-secondary)]">{stage}</span>
                      </div>
                      <span className="font-mono text-[11px] text-[var(--text-muted)]">
                        {Math.round(progress * 100)}%
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-3)]">
                      <div
                        className="h-full rounded-full bg-[var(--text-primary)] transition-all duration-300"
                        style={{ width: `${Math.max(progress * 100, 2)}%` }}
                      />
                    </div>
                  </div>

                  {/* Log */}
                  <div
                    className="max-h-[300px] overflow-y-auto rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] p-3 font-mono text-[11px] leading-relaxed text-[var(--text-muted)]"
                  >
                    {log.map((entry, i) => (
                      <div key={i} className="flex gap-2">
                        <span className="shrink-0 text-[var(--text-faint)]">
                          {new Date(entry.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                        <span className="text-[var(--text-secondary)]">{entry.stage}</span>
                        <span>{entry.status}</span>
                      </div>
                    ))}
                    <div ref={logEndRef} />
                  </div>
                </div>
              )}
            </CardBody>
          </Card>

          {/* Trace viewer */}
          {showTraces && traceData && (
            <Card>
              <CardBody>
                <div className="mb-3 text-[13px] font-semibold text-[var(--text-primary)]">
                  Full Traceability
                </div>
                <TraceViewer
                  traceability={traceData.traceability}
                  webSearch={traceData.web_search}
                />
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
