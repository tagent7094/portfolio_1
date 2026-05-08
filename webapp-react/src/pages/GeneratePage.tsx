import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Play, Loader2, Square, FileSpreadsheet, CheckCircle2, Eye,
  Search, X, ThumbsUp, MessageSquare, Repeat2,
  Shuffle, Library,
} from 'lucide-react'
import { streamSSE, apiGet } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import { PageHeader, Card, CardBody, Button } from '../components/ui'
import TraceViewer from '../components/TraceViewer'

interface LogEntry { stage: string; status: string; ts: number }

interface ViralSource {
  id: string
  content: string
  likes: number
  comments: number
  reposts: number
  creator: string
  content_type: string
  source: string
}

type SourceMode = 'auto' | 'pick'

export default function GeneratePage() {
  const active = useFounderStore((s) => s.active)

  const [nSources, setNSources] = useState(3)
  const [postsPerSource, setPostsPerSource] = useState(9)
  const [creativity, setCreativity] = useState(0.5)
  const [sourceMode, setSourceMode] = useState<SourceMode>('auto')
  const [selectedSources, setSelectedSources] = useState<ViralSource[]>([])

  const [viralSources, setViralSources] = useState<ViralSource[]>([])
  const [viralTotal, setViralTotal] = useState(0)
  const [viralQuery, setViralQuery] = useState('')
  const [viralLoading, setViralLoading] = useState(false)
  const [showPicker, setShowPicker] = useState(false)

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

  const totalPosts = sourceMode === 'pick'
    ? selectedSources.length * postsPerSource
    : nSources * postsPerSource

  const effectiveSources = sourceMode === 'pick' ? selectedSources.length : nSources

  const fetchViralSources = useCallback(async (query = '') => {
    setViralLoading(true)
    try {
      const data = await apiGet<{ sources: ViralSource[]; total: number }>(
        `/api/viral-sources?q=${encodeURIComponent(query)}&limit=50`
      )
      setViralSources(data.sources)
      setViralTotal(data.total)
    } catch {
      setViralSources([])
    } finally {
      setViralLoading(false)
    }
  }, [])

  useEffect(() => {
    if (showPicker) fetchViralSources(viralQuery)
  }, [showPicker, viralQuery, fetchViralSources])

  const toggleSource = (src: ViralSource) => {
    setSelectedSources(prev => {
      const exists = prev.find(s => s.id === src.id)
      if (exists) return prev.filter(s => s.id !== src.id)
      return [...prev, src]
    })
  }

  const handleGenerate = async () => {
    if (!active) {
      setError('No founder selected')
      return
    }
    if (sourceMode === 'pick' && selectedSources.length === 0) {
      setError('Select at least one source post')
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

    const body: any = {
      founder_slug: active,
      n_sources: effectiveSources,
      posts_per_source: postsPerSource,
      creativity,
      platform: 'linkedin',
    }
    if (sourceMode === 'pick') {
      body.source_posts = selectedSources.map(s => s.content)
    }

    try {
      await streamSSE(
        '/api/generate/batch/stream',
        body,
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
        subtitle={`Batch cowork engine — ${totalPosts} posts from ${effectiveSources} source${effectiveSources !== 1 ? 's' : ''}`}
      />

      <div className="grid gap-5 lg:grid-cols-[380px_1fr]">
        {/* Config panel */}
        <div className="space-y-4">
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

              {/* Source mode selector */}
              <div>
                <label className="mb-2 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                  Source Selection
                </label>
                <div className="flex rounded-lg border border-[var(--border-1)] overflow-hidden text-[12px]">
                  <button
                    onClick={() => setSourceMode('auto')}
                    disabled={generating}
                    className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 transition-colors ${
                      sourceMode === 'auto'
                        ? 'bg-[var(--text-primary)] text-[var(--surface-1)]'
                        : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
                    }`}
                  >
                    <Shuffle size={12} /> Auto-select
                  </button>
                  <button
                    onClick={() => { setSourceMode('pick'); setShowPicker(true) }}
                    disabled={generating}
                    className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 transition-colors ${
                      sourceMode === 'pick'
                        ? 'bg-[var(--text-primary)] text-[var(--surface-1)]'
                        : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
                    }`}
                  >
                    <Library size={12} /> Pick viral posts
                  </button>
                </div>
              </div>

              {sourceMode === 'auto' && (
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
                </div>
              )}

              {sourceMode === 'pick' && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                      Selected ({selectedSources.length})
                    </label>
                    <button
                      onClick={() => setShowPicker(true)}
                      disabled={generating}
                      className="text-[11px] text-[var(--text-primary)] hover:underline"
                    >
                      Browse library
                    </button>
                  </div>
                  {selectedSources.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-[var(--border-2)] p-4 text-center text-[11px] text-[var(--text-faint)]">
                      Click "Browse library" to pick viral posts
                    </div>
                  ) : (
                    <div className="space-y-1.5 max-h-[200px] overflow-y-auto">
                      {selectedSources.map(src => (
                        <div key={src.id} className="group flex items-start gap-2 rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] p-2">
                          <p className="flex-1 text-[11px] text-[var(--text-muted)] line-clamp-2">{src.content}</p>
                          <button
                            onClick={() => toggleSource(src)}
                            className="shrink-0 p-0.5 text-[var(--text-faint)] hover:text-[var(--error)] opacity-0 group-hover:opacity-100 transition-opacity"
                          >
                            <X size={12} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div>
                <label className="mb-2 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                  Posts per Source ({postsPerSource})
                </label>
                <input
                  type="range" min={1} max={9} value={postsPerSource}
                  onChange={e => setPostsPerSource(Number(e.target.value))}
                  disabled={generating}
                  className="w-full accent-[var(--text-primary)]"
                />
                <div className="mt-1 flex justify-between text-[10px] text-[var(--text-faint)]">
                  <span>1</span><span>3</span><span>6</span><span>9</span>
                </div>
                <p className="mt-1.5 text-[11px] text-[var(--text-muted)]">
                  {postsPerSource <= 3
                    ? `${Math.min(postsPerSource, 3)} mirrored`
                    : `3 mirrored + ${postsPerSource - 3} mechanics`}
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
                <p className="font-semibold text-[var(--text-secondary)]">{totalPosts} posts total</p>
                <p className="mt-0.5">{effectiveSources} source{effectiveSources !== 1 ? 's' : ''} × {postsPerSource} per source</p>
                <p className="mt-0.5">5-gate amplifier + convergence test</p>
                <p className="mt-0.5">Web search enrichment + full traceability</p>
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
        </div>

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

                  <div className="max-h-[300px] overflow-y-auto rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] p-3 font-mono text-[11px] leading-relaxed text-[var(--text-muted)]">
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

      {/* Viral source picker modal */}
      {showPicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="relative w-full max-w-3xl max-h-[80vh] flex flex-col rounded-xl border border-[var(--border-1)] bg-[var(--surface-1)] shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-[var(--border-2)] px-5 py-3">
              <div>
                <h3 className="text-[14px] font-semibold text-[var(--text-primary)]">Viral Post Library</h3>
                <p className="text-[11px] text-[var(--text-muted)]">{viralTotal} posts available · {selectedSources.length} selected</p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setShowPicker(false)}
                  className="rounded-lg border border-[var(--border-1)] px-3 py-1.5 text-[12px] text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                >
                  Done
                </button>
              </div>
            </div>

            {/* Search */}
            <div className="border-b border-[var(--border-2)] px-5 py-2.5">
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)]" />
                <input
                  type="text"
                  value={viralQuery}
                  onChange={e => setViralQuery(e.target.value)}
                  placeholder="Search viral posts..."
                  className="w-full rounded-lg border border-[var(--border-1)] bg-[var(--surface-3)] pl-8 pr-3 py-2 text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-faint)] focus:outline-none focus:ring-1 focus:ring-[var(--text-primary)]"
                />
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {viralLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 size={20} className="animate-spin text-[var(--text-faint)]" />
                </div>
              ) : viralSources.length === 0 ? (
                <div className="py-12 text-center text-[12px] text-[var(--text-faint)]">
                  No viral posts found
                </div>
              ) : (
                viralSources.map(src => {
                  const isSelected = selectedSources.some(s => s.id === src.id)
                  return (
                    <button
                      key={src.id}
                      onClick={() => toggleSource(src)}
                      className={`w-full text-left rounded-lg border p-3 transition-colors ${
                        isSelected
                          ? 'border-[var(--text-primary)] bg-[var(--text-primary)]/5'
                          : 'border-[var(--border-2)] bg-[var(--surface-2)] hover:border-[var(--border-1)]'
                      }`}
                    >
                      <p className="text-[12px] text-[var(--text-secondary)] line-clamp-3 leading-relaxed">
                        {src.content}
                      </p>
                      <div className="mt-2 flex items-center gap-3 text-[10px] text-[var(--text-faint)]">
                        {src.likes > 0 && (
                          <span className="flex items-center gap-1">
                            <ThumbsUp size={10} /> {src.likes.toLocaleString()}
                          </span>
                        )}
                        {src.comments > 0 && (
                          <span className="flex items-center gap-1">
                            <MessageSquare size={10} /> {src.comments.toLocaleString()}
                          </span>
                        )}
                        {src.reposts > 0 && (
                          <span className="flex items-center gap-1">
                            <Repeat2 size={10} /> {src.reposts.toLocaleString()}
                          </span>
                        )}
                        {src.content_type && (
                          <span className="rounded bg-[var(--surface-3)] px-1.5 py-0.5">{src.content_type}</span>
                        )}
                        {src.source === 'curated' && (
                          <span className="rounded bg-[var(--text-primary)]/10 px-1.5 py-0.5 text-[var(--text-primary)]">curated</span>
                        )}
                        {isSelected && (
                          <span className="ml-auto font-semibold text-[var(--text-primary)]">Selected</span>
                        )}
                      </div>
                    </button>
                  )
                })
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
