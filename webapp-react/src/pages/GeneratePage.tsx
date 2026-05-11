import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Play, Loader2, Square, FileSpreadsheet, CheckCircle2, Eye,
  Search, X, ThumbsUp, MessageSquare, Repeat2,
  Shuffle, Library, Brain, Download, ExternalLink,
  ChevronDown, ChevronUp, Save, Circle, ClipboardPaste,
} from 'lucide-react'
import clsx from 'clsx'
import { streamSSE, apiGet, apiPost } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import { PageHeader, Card, CardBody, Button } from '../components/ui'
import TraceViewer from '../components/TraceViewer'
import {
  ALL_GROUPS,
  PostTable, DetailPanel, PackSummary, exportExcel,
  type PackData,
} from '../components/pack-table'

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

type SourceMode = 'auto' | 'pick' | 'paste'

export default function GeneratePage() {
  const active = useFounderStore((s) => s.active)
  const navigate = useNavigate()

  const [nSources, setNSources] = useState(3)
  const [postsPerSource, setPostsPerSource] = useState(9)
  const [creativity, setCreativity] = useState(0.5)
  const [enableThinking, setEnableThinking] = useState(true)
  const [effort, setEffort] = useState<'low' | 'medium' | 'high'>('high')
  const [sourceMode, setSourceMode] = useState<SourceMode>('auto')
  const [selectedSources, setSelectedSources] = useState<ViralSource[]>([])
  const [customPosts, setCustomPosts] = useState<string[]>([''])

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
  const lastFilepathRef = useRef<string>('')

  // Pack display state
  const [packData, setPackData] = useState<PackData | null>(null)
  const [loadingPack, setLoadingPack] = useState(false)
  const [selectedPost, setSelectedPost] = useState<Record<string, any> | null>(null)
  const [visibleGroups, setVisibleGroups] = useState<Set<string>>(new Set(ALL_GROUPS))
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({})
  const [groupMenuOpen, setGroupMenuOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showRawLog, setShowRawLog] = useState(false)

  const pastedCount = customPosts.filter(p => p.trim().length > 0).length

  const totalPosts = sourceMode === 'pick'
    ? selectedSources.length * postsPerSource
    : sourceMode === 'paste'
    ? pastedCount * postsPerSource
    : nSources * postsPerSource

  const effectiveSources = sourceMode === 'pick'
    ? selectedSources.length
    : sourceMode === 'paste'
    ? pastedCount
    : nSources

  interface PipelineStep {
    id: string
    label: string
    status: 'pending' | 'active' | 'done'
  }

  const buildSteps = useCallback((): PipelineStep[] => {
    const steps: PipelineStep[] = [
      { id: 'internalize', label: `Read ${active || 'founder'} corpus deeply (voice, scenes, cast, rhythm, formatting)`, status: 'pending' },
      { id: 'calibration', label: 'Calibrate voice fidelity', status: 'pending' },
      { id: 'web_search', label: 'Web-verify facts and figures from source posts', status: 'pending' },
      { id: 'select_sources', label: `Pick top ${effectiveSources} viral source posts for adaptation`, status: 'pending' },
    ]
    for (let i = 1; i <= effectiveSources; i++) {
      steps.push({
        id: `pack_${i}`,
        label: `Build Source ${i} → ${postsPerSource} post pack + amplifier pass`,
        status: 'pending',
      })
    }
    steps.push({ id: 'compile', label: 'Compile output & save', status: 'pending' })
    return steps
  }, [active, effectiveSources, postsPerSource])

  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([])

  useEffect(() => {
    if (generating && pipelineSteps.length === 0) {
      setPipelineSteps(buildSteps())
    }
  }, [generating, pipelineSteps.length, buildSteps])

  useEffect(() => {
    if (log.length === 0) return
    const latest = log[log.length - 1]
    setPipelineSteps(prev => {
      if (prev.length === 0) return prev
      return prev.map(step => {
        if (latest.stage === step.id || latest.stage.startsWith(step.id)) {
          if (latest.status === 'completed' || latest.status === 'pipeline_done') {
            return { ...step, status: 'done' as const }
          }
          return { ...step, status: 'active' as const }
        }
        return step
      })
    })
  }, [log])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log.length])

  const handleEdit = useCallback((rowId: string, colKey: string, value: string) => {
    setEdits(prev => ({
      ...prev,
      [rowId]: { ...(prev[rowId] || {}), [colKey]: value },
    }))
  }, [])

  const editCount = useMemo(
    () => Object.values(edits).reduce((sum, row) => sum + Object.keys(row).length, 0),
    [edits],
  )

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

  const fetchPackData = useCallback(async () => {
    if (!lastPackDateRef.current || !active) return
    setLoadingPack(true)
    try {
      const fname = lastFilepathRef.current?.split(/[/\\]/).pop() || ''
      const qs = fname ? `?filename=${encodeURIComponent(fname)}` : ''
      const data = await apiGet<PackData>(
        `/api/admin/founders/${active}/post-packs/${lastPackDateRef.current}${qs}`
      )
      setPackData(data)
    } catch {
      // Pack display is optional — don't block on failure
    } finally {
      setLoadingPack(false)
    }
  }, [active])

  const handleGenerate = async () => {
    if (!active) {
      setError('No founder selected')
      return
    }
    if (sourceMode === 'pick' && selectedSources.length === 0) {
      setError('Select at least one source post')
      return
    }
    if (sourceMode === 'paste' && pastedCount === 0) {
      setError('Paste at least one source post')
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
    setPackData(null)
    setSelectedPost(null)
    setEdits({})
    setPipelineSteps(buildSteps())

    const abort = new AbortController()
    abortRef.current = abort

    const body: any = {
      founder_slug: active,
      n_sources: effectiveSources,
      posts_per_source: postsPerSource,
      creativity,
      enable_thinking: enableThinking,
      effort,
      platform: 'linkedin',
    }
    if (sourceMode === 'pick') {
      body.source_posts = selectedSources.map(s => s.content)
    } else if (sourceMode === 'paste') {
      body.source_posts = customPosts.filter(p => p.trim().length > 0)
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
            lastFilepathRef.current = event.data.filepath
            const match = event.data.filepath.match(/(\d{4}-\d{2}-\d{2})/)
            if (match) lastPackDateRef.current = match[1]
          }
          if (event.data?.error) {
            setError(event.data.error)
          }
          if (event.data?.cancelled) {
            setStage('Cancelled')
            setGenerating(false)
            return
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

  // Fetch pack data once generation completes
  useEffect(() => {
    if (done && lastPackDateRef.current && active) {
      fetchPackData()
    }
  }, [done, active, fetchPackData])

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

  const handleSaveEdits = async () => {
    if (!active || !lastPackDateRef.current || editCount === 0) return
    setSaving(true)
    try {
      await apiPost(`/api/admin/founders/${active}/post-packs/${lastPackDateRef.current}/edits`, { edits })
      setEdits({})
    } catch {
      // silently fail — user can retry
    } finally {
      setSaving(false)
    }
  }

  const handleExportExcel = () => {
    if (!packData) return
    const filename = `${active}_batch_${lastPackDateRef.current}`
    exportExcel(packData.posts, packData.headers, edits, filename)
  }

  const filenameDisplay = lastFilepathRef.current
    ? lastFilepathRef.current.split(/[/\\]/).pop() || ''
    : ''

  const toggleGroup = (g: string) => {
    setVisibleGroups(prev => {
      const next = new Set(prev)
      if (next.has(g)) next.delete(g)
      else next.add(g)
      return next
    })
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
                    <Library size={12} /> Pick posts
                  </button>
                  <button
                    onClick={() => setSourceMode('paste')}
                    disabled={generating}
                    className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2 transition-colors ${
                      sourceMode === 'paste'
                        ? 'bg-[var(--text-primary)] text-[var(--surface-1)]'
                        : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
                    }`}
                  >
                    <ClipboardPaste size={12} /> Paste custom
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

              {sourceMode === 'paste' && (
                <div>
                  <label className="mb-2 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                    Custom Source Posts ({pastedCount})
                  </label>
                  <div className="space-y-2 max-h-[300px] overflow-y-auto">
                    {customPosts.map((post, idx) => (
                      <div key={idx} className="relative">
                        <textarea
                          value={post}
                          onChange={e => {
                            const next = [...customPosts]
                            next[idx] = e.target.value
                            setCustomPosts(next)
                          }}
                          disabled={generating}
                          placeholder={`Paste source post ${idx + 1}...`}
                          rows={4}
                          className="w-full rounded-lg border border-[var(--border-1)] bg-[var(--surface-3)] px-3 py-2 text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-faint)] focus:outline-none focus:ring-1 focus:ring-[var(--text-primary)] resize-y"
                        />
                        {customPosts.length > 1 && (
                          <button
                            onClick={() => setCustomPosts(customPosts.filter((_, i) => i !== idx))}
                            disabled={generating}
                            className="absolute right-2 top-2 rounded p-0.5 text-[var(--text-faint)] hover:text-[var(--error)] transition-colors"
                          >
                            <X size={12} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                  <button
                    onClick={() => setCustomPosts([...customPosts, ''])}
                    disabled={generating}
                    className="mt-2 w-full rounded-lg border border-dashed border-[var(--border-2)] py-2 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:border-[var(--border-1)] transition-colors"
                  >
                    + Add another source post
                  </button>
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

              {/* Thinking toggle */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Brain size={14} className={enableThinking ? 'text-amber-400' : 'text-[var(--text-faint)]'} />
                  <div>
                    <div className="text-[12px] text-[var(--text-secondary)]">Extended Thinking</div>
                    <div className="text-[10px] text-[var(--text-faint)]">
                      {enableThinking ? 'Model reasons before generating' : 'Direct generation (faster)'}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => setEnableThinking(!enableThinking)}
                  disabled={generating}
                  className={`relative h-5 w-9 rounded-full transition-colors ${
                    enableThinking ? 'bg-amber-500' : 'bg-[var(--surface-3)]'
                  }`}
                >
                  <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                    enableThinking ? 'translate-x-4' : 'translate-x-0.5'
                  }`} />
                </button>
              </div>

              {/* Thinking effort */}
              {enableThinking && (
                <div>
                  <label className="mb-2 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                    Thinking Effort
                  </label>
                  <div className="flex rounded-lg border border-[var(--border-1)] overflow-hidden text-[12px]">
                    {(['low', 'medium', 'high'] as const).map(level => (
                      <button
                        key={level}
                        onClick={() => setEffort(level)}
                        disabled={generating}
                        className={`flex-1 px-3 py-2 capitalize transition-colors ${
                          effort === level
                            ? 'bg-[var(--text-primary)] text-[var(--surface-1)]'
                            : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
                        }`}
                      >
                        {level}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] p-3 text-[12px] text-[var(--text-muted)]">
                <p className="font-semibold text-[var(--text-secondary)]">{totalPosts} posts total</p>
                <p className="mt-0.5">{effectiveSources} source{effectiveSources !== 1 ? 's' : ''} × {postsPerSource} per source</p>
                <p className="mt-0.5">5-gate amplifier + convergence test</p>
                <p className="mt-0.5">Web search enrichment + full traceability</p>
                {enableThinking && <p className="mt-0.5 text-amber-400/60">Extended thinking enabled (visible in traces)</p>}
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
                  {filenameDisplay && (
                    <div className="rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] px-3 py-2 text-[11px] text-[var(--text-muted)]">
                      Auto-saved to <span className="font-mono text-[var(--text-secondary)]">{filenameDisplay}</span>
                    </div>
                  )}
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
                    onClick={() => {
                      setDone(false)
                      setTraceData(null)
                      setShowTraces(false)
                      setPackData(null)
                      setSelectedPost(null)
                      setEdits({})
                      setPipelineSteps([])
                      setLog([])
                      setProgress(0)
                      setStage('')
                    }}
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
                  {/* Progress header */}
                  <div>
                    <div className="mb-1.5 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {generating && <Loader2 size={12} className="animate-spin text-[var(--text-primary)]" />}
                        {done && <CheckCircle2 size={12} className="text-[var(--success)]" />}
                        <span className="text-[13px] font-semibold text-[var(--text-primary)]">Progress</span>
                        {stage && <span className="text-[11px] text-[var(--text-faint)]">— {stage}</span>}
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

                  {/* Checklist */}
                  <div className="space-y-1">
                    {pipelineSteps.map(step => (
                      <div key={step.id} className="flex items-start gap-3 py-1.5">
                        <div className="mt-0.5 shrink-0">
                          {step.status === 'done' && (
                            <CheckCircle2 size={18} className="text-blue-500" />
                          )}
                          {step.status === 'active' && (
                            <Loader2 size={18} className="animate-spin text-blue-500" />
                          )}
                          {step.status === 'pending' && (
                            <Circle size={18} className="text-[var(--text-faint)]" />
                          )}
                        </div>
                        <span className={clsx(
                          'text-[13px] leading-snug',
                          step.status === 'done' && 'text-[var(--text-faint)] line-through',
                          step.status === 'active' && 'text-[var(--text-primary)] font-medium',
                          step.status === 'pending' && 'text-[var(--text-muted)]',
                        )}>
                          {step.label}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* Collapsible raw log */}
                  <button
                    onClick={() => setShowRawLog(!showRawLog)}
                    className="flex items-center gap-1.5 text-[11px] text-[var(--text-faint)] hover:text-[var(--text-muted)] transition-colors"
                  >
                    {showRawLog ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    Raw log ({log.length} events)
                  </button>
                  {showRawLog && (
                    <div className="max-h-[200px] overflow-y-auto rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] p-3 font-mono text-[11px] leading-relaxed text-[var(--text-muted)]">
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
                  )}
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

      {/* Generated posts table — full width below the two-column grid */}
      {loadingPack && (
        <div className="mt-5 flex items-center justify-center gap-2 py-12 text-[var(--text-muted)]">
          <Loader2 size={16} className="animate-spin" />
          <span className="text-[13px]">Loading generated posts...</span>
        </div>
      )}

      {packData && (
        <div className="mt-5 space-y-4">
          {/* Action bar */}
          <Card>
            <CardBody className="flex flex-wrap items-center gap-3 py-3">
              <div className="flex-1 min-w-0">
                <h3 className="text-[13px] font-semibold text-[var(--text-primary)]">
                  Generated Posts
                </h3>
                <p className="text-[11px] text-[var(--text-muted)]">
                  {packData.posts.length} posts · {lastPackDateRef.current}
                </p>
              </div>

              {/* Column group toggles */}
              <div className="relative">
                <button
                  onClick={() => setGroupMenuOpen(!groupMenuOpen)}
                  className="flex items-center gap-1.5 rounded-lg border border-[var(--border-1)] px-3 py-1.5 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
                >
                  <Eye size={12} />
                  Columns
                  <ChevronDown size={10} className={clsx('transition-transform', groupMenuOpen && 'rotate-180')} />
                </button>
                {groupMenuOpen && (
                  <>
                    <div className="fixed inset-0 z-40" onClick={() => setGroupMenuOpen(false)} />
                    <div className="absolute right-0 top-full z-50 mt-1 w-48 rounded-lg border border-[var(--border-1)] bg-[var(--surface-1)] py-1 shadow-xl">
                      {ALL_GROUPS.map(g => (
                        <button
                          key={g}
                          onClick={() => toggleGroup(g)}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-[11px] hover:bg-[var(--surface-2)] transition-colors"
                        >
                          <span className={clsx(
                            'h-3 w-3 rounded border flex items-center justify-center text-[8px]',
                            visibleGroups.has(g)
                              ? 'border-[var(--text-primary)] bg-[var(--text-primary)] text-white'
                              : 'border-[var(--border-1)]'
                          )}>
                            {visibleGroups.has(g) && '✓'}
                          </span>
                          <span className="text-[var(--text-secondary)]">{g}</span>
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <button
                onClick={handleExportExcel}
                className="flex items-center gap-1.5 rounded-lg border border-[var(--border-1)] px-3 py-1.5 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
              >
                <Download size={12} />
                Download Excel
              </button>

              {active && lastPackDateRef.current && (
                <button
                  onClick={() => navigate(`/admin/founders/${active}?date=${lastPackDateRef.current}`)}
                  className="flex items-center gap-1.5 rounded-lg border border-[var(--border-1)] px-3 py-1.5 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
                >
                  <ExternalLink size={12} />
                  Open in Pack Viewer
                </button>
              )}

              {editCount > 0 && (
                <button
                  onClick={handleSaveEdits}
                  disabled={saving}
                  className="flex items-center gap-1.5 rounded-lg bg-[var(--text-primary)] px-3 py-1.5 text-[11px] text-[var(--surface-1)] hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                  Save {editCount} edit{editCount !== 1 ? 's' : ''}
                </button>
              )}
            </CardBody>
          </Card>

          {/* Summary */}
          {packData.readme && Object.keys(packData.readme).length > 0 && (
            <Card>
              <CardBody className="py-3">
                <PackSummary readme={packData.readme} />
              </CardBody>
            </Card>
          )}

          {/* Source posts used */}
          {(() => {
            const sourceMap = new Map<number, string>()
            packData.posts.forEach(p => {
              const src = Number(p['Source #'])
              if (src && !sourceMap.has(src) && p['Source Post']) {
                sourceMap.set(src, String(p['Source Post']))
              }
            })
            if (sourceMap.size === 0) return null
            return (
              <Card>
                <CardBody className="py-3 space-y-3">
                  <h4 className="text-[12px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                    Source Posts Used
                  </h4>
                  {Array.from(sourceMap.entries()).map(([num, text]) => (
                    <details key={num} className="group">
                      <summary className="cursor-pointer text-[12px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
                        Source {num}
                        <span className="ml-2 text-[var(--text-faint)] font-normal">
                          {text.slice(0, 120)}...
                        </span>
                      </summary>
                      <div className="mt-2 rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] p-3 text-[12px] leading-relaxed text-[var(--text-muted)] whitespace-pre-wrap max-h-[400px] overflow-y-auto">
                        {text}
                      </div>
                    </details>
                  ))}
                </CardBody>
              </Card>
            )
          })()}

          {/* Table */}
          <Card>
            <div style={{ height: 'min(60vh, 600px)' }}>
              <PostTable
                posts={packData.posts}
                headers={packData.headers}
                selectedPost={selectedPost}
                onSelectRow={setSelectedPost}
                visibleGroups={visibleGroups}
                edits={edits}
                onEdit={handleEdit}
              />
            </div>
          </Card>
        </div>
      )}

      {/* Detail panel */}
      {selectedPost && packData && (
        <DetailPanel
          post={selectedPost}
          headers={packData.headers}
          edits={edits}
          onEdit={handleEdit}
          onClose={() => setSelectedPost(null)}
        />
      )}

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
