import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Play, Loader2, Square, FileSpreadsheet, CheckCircle2, Eye,
  Search, X, ThumbsUp, MessageSquare, Repeat2, Star,
  Shuffle, Library, Brain, Download, ExternalLink,
  ChevronDown, ChevronUp, Save, Circle, ClipboardPaste, SlidersHorizontal,
  Clock, Trash2, Power, Zap,
} from 'lucide-react'
import clsx from 'clsx'
import { apiGet, apiPost, apiDelete } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import { PageHeader, Card, CardBody, Button } from '../components/ui'
import TraceViewer from '../components/TraceViewer'
import PostCustomizer from '../components/PostCustomizer'
import CornerChatbot from '../components/CornerChatbot'
import CustomizeSection from '../components/CustomizeSection'
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
  source_sheet?: string
  match_score?: number
  matched_keywords?: number
  topic_score?: number
  mechanics_score?: number
  audience_score?: number
  match_reason?: string
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
  const [lean, setLean] = useState(false)
  const [sourceMode, setSourceMode] = useState<SourceMode>('auto')
  const [selectedSources, setSelectedSources] = useState<ViralSource[]>([])
  const [customPosts, setCustomPosts] = useState<string[]>([''])

  const [viralSources, setViralSources] = useState<ViralSource[]>([])
  const [viralTotal, setViralTotal] = useState(0)
  const [viralQuery, setViralQuery] = useState('')
  const [viralLoading, setViralLoading] = useState(false)
  const [showPicker, setShowPicker] = useState(false)
  const [vpMinLikes, setVpMinLikes] = useState('')
  const [vpMaxLikes, setVpMaxLikes] = useState('')
  const [vpMinComments, setVpMinComments] = useState('')
  const [vpMaxComments, setVpMaxComments] = useState('')
  const [vpSortBy, setVpSortBy] = useState('engagement_score')
  const [vpSheet, setVpSheet] = useState('')
  const [vpSheets, setVpSheets] = useState<string[]>([])
  const [vpPage, setVpPage] = useState(1)
  const [vpDeep, setVpDeep] = useState(false)
  const [usedSourceHashes, setUsedSourceHashes] = useState<Set<string>>(new Set())

  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState('')
  const [log, setLog] = useState<LogEntry[]>([])
  const [llmText, setLlmText] = useState('')
  const [webSearchSummary, setWebSearchSummary] = useState<any>(null)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [showTraces, setShowTraces] = useState(false)
  const [traceData, setTraceData] = useState<any>(null)
  const [loadingTraces, setLoadingTraces] = useState(false)
  const [bgTaskId, setBgTaskId] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const logOffsetRef = useRef(0)
  const logEndRef = useRef<HTMLDivElement>(null)
  const lastPackDateRef = useRef<string>('')
  const lastFilepathRef = useRef<string>('')

  // Pack display state
  const [packData, setPackData] = useState<PackData | null>(null)
  const [loadingPack, setLoadingPack] = useState(false)
  const [selectedPost, setSelectedPost] = useState<Record<string, any> | null>(null)
  const [showDetail, setShowDetail] = useState(false)
  const [custVariant, setCustVariant] = useState<{ letter: string; opener: string; originalBody: string } | null>(null)
  const [custPost, setCustPost] = useState('')
  const [visibleGroups, setVisibleGroups] = useState<Set<string>>(new Set(ALL_GROUPS))
  const [edits, setEdits] = useState<Record<string, Record<string, string>>>({})
  const [groupMenuOpen, setGroupMenuOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showRawLog, setShowRawLog] = useState(false)
  const [custApiKey, setCustApiKey] = useState(() => localStorage.getItem('asksharath_api_key') || '')

  // Schedule state
  interface ScheduleItem { id: string; founder_slug: string; hour: number; minute: number; days: string[]; n_sources: number; posts_per_source: number; creativity: number; effort: string; enabled: boolean; last_run: string | null; last_status: string | null }
  const [showScheduleModal, setShowScheduleModal] = useState(false)
  const [schedHour, setSchedHour] = useState(9)
  const [schedMinute, setSchedMinute] = useState(0)
  const [schedDays, setSchedDays] = useState(['mon', 'tue', 'wed', 'thu', 'fri'])
  const [savingSchedule, setSavingSchedule] = useState(false)
  const [founderSchedules, setFounderSchedules] = useState<ScheduleItem[]>([])

  const refreshFounderSchedules = useCallback(async () => {
    if (!active) return
    try {
      const data = await apiGet<{ schedules: ScheduleItem[] }>('/api/admin/schedules')
      setFounderSchedules(data.schedules.filter(s => s.founder_slug === active))
    } catch {}
  }, [active])

  useEffect(() => { refreshFounderSchedules() }, [refreshFounderSchedules])

  const createSchedule = async () => {
    if (!active) return
    setSavingSchedule(true)
    try {
      await apiPost('/api/admin/schedules', {
        founder_slug: active,
        hour: schedHour,
        minute: schedMinute,
        days: schedDays,
        n_sources: nSources,
        posts_per_source: postsPerSource,
        creativity,
        effort,
      })
      await refreshFounderSchedules()
      setShowScheduleModal(false)
    } catch (err: any) { alert(`Failed: ${err?.message}`) }
    finally { setSavingSchedule(false) }
  }

  const deleteFounderSchedule = async (id: string) => {
    try {
      await apiDelete(`/api/admin/schedules/${id}`)
      await refreshFounderSchedules()
    } catch {}
  }

  const toggleFounderSchedule = async (id: string) => {
    try {
      await apiPost(`/api/admin/schedules/${id}/toggle`, {})
      await refreshFounderSchedules()
    } catch {}
  }

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
    setPipelineSteps(prev => {
      if (prev.length === 0) return prev
      const completed = new Set<string>()
      const started = new Set<string>()
      for (const entry of log) {
        for (const step of prev) {
          if (entry.stage === step.id || entry.stage.startsWith(step.id)) {
            if (entry.status === 'completed' || entry.status === 'pipeline_done') completed.add(step.id)
            if (entry.status === 'started' || entry.status === 'progress') started.add(step.id)
          }
        }
      }
      let lastActiveIdx = -1
      const updated = prev.map((step, idx) => {
        if (completed.has(step.id)) return { ...step, status: 'done' as const }
        if (started.has(step.id)) { lastActiveIdx = idx; return { ...step, status: 'active' as const } }
        return step
      })
      return updated.map((step, idx) =>
        step.status === 'pending' && idx < lastActiveIdx
          ? { ...step, status: 'done' as const }
          : step
      )
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

  const fetchViralSources = useCallback(async () => {
    setViralLoading(true)
    try {
      const params = new URLSearchParams()
      if (viralQuery) params.set('q', viralQuery)
      if (vpMinLikes) params.set('min_likes', vpMinLikes)
      if (vpMaxLikes) params.set('max_likes', vpMaxLikes)
      if (vpMinComments) params.set('min_comments', vpMinComments)
      if (vpMaxComments) params.set('max_comments', vpMaxComments)
      if (vpSheet) params.set('source_sheet', vpSheet)
      params.set('limit', '20')
      params.set('offset', String((vpPage - 1) * 20))

      let data: { sources: ViralSource[]; total: number; deep?: boolean }
      if (vpSortBy === 'best_match' && active) {
        params.set('page', String(vpPage))
        params.set('page_size', '20')
        const hdrs: Record<string, string> = {}
        if (vpDeep && custApiKey) {
          params.set('deep', 'true')
          hdrs['x-rerank-api-key'] = custApiKey
        }
        data = await apiGet(`/api/viral-posts/best-match/${active}?${params}`, hdrs)
      } else {
        params.set('sort_by', vpSortBy)
        data = await apiGet(`/api/viral-sources?${params}`)
      }
      setViralSources(data.sources || [])
      setViralTotal(data.total || 0)
    } catch {
      setViralSources([])
    } finally {
      setViralLoading(false)
    }
  }, [viralQuery, vpMinLikes, vpMaxLikes, vpMinComments, vpMaxComments, vpSortBy, vpSheet, vpPage, active, vpDeep, custApiKey])

  useEffect(() => {
    if (showPicker) {
      fetchViralSources()
      apiGet<{ sheets: string[] }>('/api/viral-sources/sheets').then(d => setVpSheets(d.sheets)).catch(() => {})
      if (active) {
        apiGet<{ sources: { source_hash: string; source_snippet: string }[] }>(`/api/founders/${active}/used-sources`)
          .then(d => setUsedSourceHashes(new Set(d.sources.map(s => s.source_snippet.toLowerCase().replace(/\s+/g, ' ').trim()))))
          .catch(() => {})
      }
    }
  }, [showPicker, fetchViralSources, active])

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
        `/api/founders/${active}/post-packs/${lastPackDateRef.current}${qs}`
      )
      setPackData(data)
    } catch {
      // Pack display is optional — don't block on failure
    } finally {
      setLoadingPack(false)
    }
  }, [active])

  const startPolling = useCallback((taskId: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    logOffsetRef.current = 0
    pollRef.current = setInterval(async () => {
      try {
        const res = await apiGet<any>(`/api/generate/batch/status/${taskId}?since=${logOffsetRef.current}`)
        setProgress(res.progress || 0)
        setStage(res.stage || '')
        if (res.current_llm_text) setLlmText(res.current_llm_text)
        if (res.web_search_summary) setWebSearchSummary(res.web_search_summary)
        if (res.log?.length) {
          setLog(prev => [...prev, ...res.log.map((l: any) => ({ stage: l.stage, status: l.status, ts: Date.now() }))])
          logOffsetRef.current = res.log_offset
        }
        if (res.filepath) {
          lastFilepathRef.current = res.filepath
          const match = res.filepath.match(/(\d{4}-\d{2}-\d{2})/)
          if (match) lastPackDateRef.current = match[1]
        }
        if (res.error) setError(res.error)
        if (res.status !== 'running') {
          clearInterval(pollRef.current!)
          pollRef.current = null
          setBgTaskId(null)
          setLlmText('')
          localStorage.removeItem(`gen_task_${active}`)
          if (res.status === 'done') {
            setDone(true)
            setGenerating(false)
          } else {
            setGenerating(false)
            if (res.status === 'cancelled') setStage('Cancelled')
          }
        }
      } catch {
        // retry on next poll
      }
    }, 3000)
  }, [active])

  // Resume polling on mount if a task was running
  useEffect(() => {
    if (!active) return
    const savedTask = localStorage.getItem(`gen_task_${active}`)
    if (savedTask) {
      setBgTaskId(savedTask)
      setGenerating(true)
      setStage('resuming...')
      setPipelineSteps(buildSteps())
      startPolling(savedTask)
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [active, startPolling, buildSteps])

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
    setStage('starting...')
    setLog([])
    setDone(false)
    setError('')
    setTraceData(null)
    setShowTraces(false)
    setPackData(null)
    setSelectedPost(null)
    setShowDetail(false)
    setEdits({})
    setPipelineSteps(buildSteps())

    const body: any = {
      founder_slug: active,
      n_sources: effectiveSources,
      posts_per_source: postsPerSource,
      creativity,
      enable_thinking: enableThinking,
      effort,
      lean,
      platform: 'linkedin',
    }
    if (sourceMode === 'pick') {
      body.source_posts = selectedSources.map(s => s.content)
    } else if (sourceMode === 'paste') {
      body.source_posts = customPosts.filter(p => p.trim().length > 0)
    }

    try {
      const res = await apiPost<{ task_id: string }>('/api/generate/batch/background', body)
      setBgTaskId(res.task_id)
      localStorage.setItem(`gen_task_${active}`, res.task_id)
      startPolling(res.task_id)
    } catch (e: any) {
      setError(e?.message || 'Failed to start generation')
      setGenerating(false)
    }
  }

  // Fetch pack data once generation completes
  useEffect(() => {
    if (done && lastPackDateRef.current && active) {
      fetchPackData()
    }
  }, [done, active, fetchPackData])

  const handleCancel = async () => {
    if (bgTaskId) {
      try { await apiPost(`/api/generate/batch/cancel/${bgTaskId}`, {}) } catch {}
      localStorage.removeItem(`gen_task_${active}`)
    }
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    setBgTaskId(null)
    setGenerating(false)
  }

  const loadTraces = async () => {
    if (!lastPackDateRef.current || !active) return
    setLoadingTraces(true)
    try {
      const data = await apiGet<any>(`/api/founders/${active}/post-packs/${lastPackDateRef.current}/traces`)
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

              {/* Lean mode toggle */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Zap size={14} className={lean ? 'text-green-400' : 'text-[var(--text-faint)]'} />
                  <div>
                    <div className="text-[12px] text-[var(--text-secondary)]">Lean Mode</div>
                    <div className="text-[10px] text-[var(--text-faint)]">
                      {lean ? 'Batched calls (~8 per source) — for rate-limited providers' : 'Standard pipeline (~39 calls per source)'}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => setLean(!lean)}
                  disabled={generating}
                  className={`relative h-5 w-9 rounded-full transition-colors ${
                    lean ? 'bg-green-500' : 'bg-[var(--surface-3)]'
                  }`}
                >
                  <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                    lean ? 'translate-x-4' : 'translate-x-0.5'
                  }`} />
                </button>
              </div>

              <div className="rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] p-3 text-[12px] text-[var(--text-muted)]">
                <p className="font-semibold text-[var(--text-secondary)]">{totalPosts} posts total</p>
                <p className="mt-0.5">{effectiveSources} source{effectiveSources !== 1 ? 's' : ''} × {postsPerSource} per source</p>
                <p className="mt-0.5">5-gate amplifier + convergence test</p>
                <p className="mt-0.5">Web search enrichment + full traceability</p>
                {enableThinking && <p className="mt-0.5 text-amber-400/60">Extended thinking enabled (visible in traces)</p>}
              </div>

              {!generating && !done && (
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    className="flex-1"
                    onClick={handleGenerate}
                    icon={<Play size={14} />}
                  >
                    Start Generation
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => setShowScheduleModal(true)}
                    icon={<Clock size={14} />}
                    title="Schedule recurring generation"
                  >
                    Schedule
                  </Button>
                </div>
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
                      setShowDetail(false)
                      setCustVariant(null)
                      setCustPost('')
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

              {/* Active schedules for this founder */}
              {founderSchedules.length > 0 && (
                <div className="mt-4 space-y-1.5">
                  <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                    <Clock size={10} /> Schedules
                  </div>
                  {founderSchedules.map(s => (
                    <div key={s.id} className="flex items-center gap-2 rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] px-3 py-2 text-[11px]">
                      <button onClick={() => toggleFounderSchedule(s.id)} title={s.enabled ? 'Disable' : 'Enable'}>
                        <Power size={12} className={s.enabled ? 'text-[var(--success)]' : 'text-[var(--text-faint)]'} />
                      </button>
                      <span className="flex-1 text-[var(--text-secondary)]">
                        {String(s.hour).padStart(2, '0')}:{String(s.minute).padStart(2, '0')} IST · {s.days.map(d => d.slice(0, 2)).join(' ')}
                        <span className="ml-1.5 text-[var(--text-faint)]">{s.n_sources}src × {s.posts_per_source}p</span>
                      </span>
                      {s.last_status && (
                        <span className={`text-[10px] ${s.last_status === 'success' ? 'text-[var(--success)]' : 'text-[var(--error)]'}`}>
                          {s.last_status === 'success' ? 'OK' : 'err'}
                        </span>
                      )}
                      <button onClick={() => deleteFounderSchedule(s.id)} className="text-[var(--text-faint)] hover:text-[var(--error)] transition-colors">
                        <Trash2 size={11} />
                      </button>
                    </div>
                  ))}
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
                        <div>
                          <span className={clsx(
                            'text-[13px] leading-snug',
                            step.status === 'done' && 'text-[var(--text-faint)] line-through',
                            step.status === 'active' && 'text-[var(--text-primary)] font-medium',
                            step.status === 'pending' && 'text-[var(--text-muted)]',
                          )}>
                            {step.label}
                          </span>
                          {step.id === 'web_search' && step.status === 'done' && webSearchSummary && (
                            <div className="mt-1 ml-0.5 text-[11px] space-y-0.5" style={{ color: 'var(--text-muted)' }}>
                              {webSearchSummary.search_queries?.map((q: string, i: number) => (
                                <div key={i} className="flex items-center gap-1.5">
                                  <span style={{ color: 'var(--text-faint)' }}>searched:</span> {q}
                                </div>
                              ))}
                              {webSearchSummary.trending_topics?.length > 0 && (
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <span style={{ color: 'var(--text-faint)' }}>topics:</span>
                                  {webSearchSummary.trending_topics.slice(0, 5).map((t: string, i: number) => (
                                    <span key={i} className="rounded-full px-1.5 py-0.5 text-[10px]"
                                      style={{ backgroundColor: 'var(--surface-3)', color: 'var(--text-secondary)' }}>
                                      {t}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Live LLM output */}
                  {generating && llmText && (
                    <div className="rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] p-3 font-mono text-[11px] max-h-[200px] overflow-y-auto whitespace-pre-wrap">
                      <div className="text-[9px] font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--text-faint)' }}>
                        Live Output
                      </div>
                      <span style={{ color: 'var(--text-muted)' }}>{llmText}</span>
                      <span className="inline-block w-[2px] h-[10px] ml-0.5 animate-pulse bg-[var(--text-primary)]" />
                    </div>
                  )}

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

      {/* Instant swap preview — no LLM, just opener replaced */}
      {!custVariant && custPost && (
        <div className="mt-5 rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-1)' }}>
          <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: 'var(--border-2)' }}>
            <span className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>Swapped Post</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => { navigator.clipboard.writeText(custPost) }}
                className="px-3 py-1 rounded-lg text-[11px] transition-colors hover:opacity-80"
                style={{ backgroundColor: 'var(--surface-2)', color: 'var(--text-secondary)', border: '1px solid var(--border-1)' }}
              >
                Copy
              </button>
              <button
                onClick={() => setCustPost('')}
                className="transition-opacity hover:opacity-70"
                style={{ color: 'var(--text-muted)' }}
              >
                ✕
              </button>
            </div>
          </div>
          <div className="px-5 py-4">
            <p className="text-[13px] leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--text-secondary)' }}>
              {custPost}
            </p>
          </div>
        </div>
      )}

      {/* Post customizer — above pack table */}
      {custVariant && packData && (
        <div className="mt-5 space-y-3">
          {!custApiKey && (
            <div className="flex items-center gap-2 rounded-lg border px-3 py-2"
              style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-2)' }}>
              <span className="text-[11px] shrink-0" style={{ color: 'var(--text-muted)' }}>Anthropic API Key:</span>
              <input
                type="password"
                value={custApiKey}
                onChange={e => { setCustApiKey(e.target.value); localStorage.setItem('asksharath_api_key', e.target.value) }}
                placeholder="sk-ant-..."
                className="flex-1 rounded border px-2 py-1 text-[12px] focus:outline-none"
                style={{ borderColor: 'var(--border-1)', backgroundColor: 'var(--surface-3)', color: 'var(--text-primary)' }}
              />
            </div>
          )}
          <PostCustomizer
            variant={custVariant}
            founderSlug={active || ''}
            apiKey={custApiKey}
            effort={effort}
            voiceMarkers={packData.readme?.['Voice Markers'] || ''}
            onClose={() => { setCustVariant(null); setCustPost('') }}
            onPostReady={setCustPost}
          />
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
                onSelectRow={p => { setSelectedPost(p); setShowDetail(!!p) }}
                visibleGroups={visibleGroups}
                edits={edits}
                onEdit={handleEdit}
              />
            </div>
          </Card>

          {/* Customize section — variant selection cards */}
          {selectedPost && !custVariant && (
            <CustomizeSection
              post={selectedPost}
              onSelectVariant={(letter, opener, body) => {
                setCustVariant({ letter, opener, originalBody: body })
                setCustPost('')
              }}
              onSwapOpener={(_letter, opener, body) => {
                if (!body) return
                const paragraphs = body.split('\n\n')
                paragraphs[0] = opener
                setCustPost(paragraphs.join('\n\n'))
              }}
              onShowDetails={() => setShowDetail(true)}
              onClose={() => setSelectedPost(null)}
            />
          )}
        </div>
      )}

      {/* Detail panel — opened via "Full Details" button */}
      {showDetail && selectedPost && packData && (
        <DetailPanel
          post={selectedPost}
          headers={packData.headers}
          edits={edits}
          onEdit={handleEdit}
          onClose={() => setShowDetail(false)}
          onSelectVariant={(letter, opener, body) => {
            setCustVariant({ letter, opener, originalBody: body })
            setCustPost('')
            setShowDetail(false)
          }}
          onSwapOpener={(_letter, opener, body) => {
            if (!body) return
            const paragraphs = body.split('\n\n')
            paragraphs[0] = opener
            setCustPost(paragraphs.join('\n\n'))
            setShowDetail(false)
          }}
        />
      )}

      {/* Corner chatbot for iterative edits */}
      {custVariant && custPost && (
        <CornerChatbot
          currentPost={custPost}
          onPostUpdate={setCustPost}
          founderSlug={active || ''}
          apiKey={custApiKey}
          effort={effort}
          voiceMarkers={packData?.readme?.['Voice Markers'] || ''}
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

            {/* Search + Filters */}
            <div className="border-b border-[var(--border-2)] px-5 py-2.5 space-y-2.5">
              <div className="flex gap-2 flex-wrap">
                <div className="relative flex-1 min-w-[180px]">
                  <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)]" />
                  <input
                    type="text"
                    value={viralQuery}
                    onChange={e => { setViralQuery(e.target.value); setVpPage(1) }}
                    placeholder="Search viral posts..."
                    className="w-full rounded-lg border border-[var(--border-1)] bg-[var(--surface-3)] pl-8 pr-3 py-2 text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-faint)] focus:outline-none focus:ring-1 focus:ring-[var(--text-primary)]"
                  />
                </div>
                <select
                  value={vpSortBy}
                  onChange={e => { setVpSortBy(e.target.value); setVpPage(1) }}
                  className="rounded-lg border border-[var(--border-1)] bg-[var(--surface-3)] px-2.5 py-2 text-[12px] text-[var(--text-primary)]"
                >
                  <option value="engagement_score">Sort: Engagement</option>
                  <option value="likes">Sort: Likes</option>
                  <option value="comments">Sort: Comments</option>
                  <option value="reposts">Sort: Reposts</option>
                  {active && <option value="best_match">Sort: Best Match for {active}</option>}
                </select>
                {vpSheets.length > 0 && (
                  <select
                    value={vpSheet}
                    onChange={e => { setVpSheet(e.target.value); setVpPage(1) }}
                    className="rounded-lg border border-[var(--border-1)] bg-[var(--surface-3)] px-2.5 py-2 text-[12px] text-[var(--text-primary)]"
                  >
                    <option value="">All sheets</option>
                    {vpSheets.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                )}
                {vpSortBy === 'best_match' && (
                  <button
                    onClick={() => {
                      if (!custApiKey && !vpDeep) {
                        alert('Set your Anthropic API key in Config page first')
                        return
                      }
                      setVpDeep(d => !d)
                      setVpPage(1)
                    }}
                    className={`rounded-lg border px-2.5 py-2 text-[12px] font-medium transition-colors ${
                      vpDeep
                        ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                        : 'border-[var(--border-1)] bg-[var(--surface-3)] text-[var(--text-muted)]'
                    }`}
                  >
                    <Brain size={12} className="inline mr-1" />
                    Deep Match {vpDeep ? 'ON' : 'OFF'}
                  </button>
                )}
              </div>
              {/* Engagement range filters */}
              <div className="flex gap-3 flex-wrap items-center text-[11px]">
                <SlidersHorizontal size={11} className="text-[var(--text-faint)]" />
                <div className="flex items-center gap-1">
                  <ThumbsUp size={10} className="text-[var(--text-faint)]" />
                  <input type="number" placeholder="Min" value={vpMinLikes} onChange={e => { setVpMinLikes(e.target.value); setVpPage(1) }} className="w-16 rounded border border-[var(--border-1)] bg-[var(--surface-3)] px-1.5 py-1 text-[11px] text-center text-[var(--text-primary)]" />
                  <span className="text-[var(--text-faint)]">–</span>
                  <input type="number" placeholder="Max" value={vpMaxLikes} onChange={e => { setVpMaxLikes(e.target.value); setVpPage(1) }} className="w-16 rounded border border-[var(--border-1)] bg-[var(--surface-3)] px-1.5 py-1 text-[11px] text-center text-[var(--text-primary)]" />
                </div>
                <div className="flex items-center gap-1">
                  <MessageSquare size={10} className="text-[var(--text-faint)]" />
                  <input type="number" placeholder="Min" value={vpMinComments} onChange={e => { setVpMinComments(e.target.value); setVpPage(1) }} className="w-16 rounded border border-[var(--border-1)] bg-[var(--surface-3)] px-1.5 py-1 text-[11px] text-center text-[var(--text-primary)]" />
                  <span className="text-[var(--text-faint)]">–</span>
                  <input type="number" placeholder="Max" value={vpMaxComments} onChange={e => { setVpMaxComments(e.target.value); setVpPage(1) }} className="w-16 rounded border border-[var(--border-1)] bg-[var(--surface-3)] px-1.5 py-1 text-[11px] text-center text-[var(--text-primary)]" />
                </div>
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
                  const snippet = src.content.toLowerCase().replace(/\s+/g, ' ').trim().slice(0, 120)
                  const isUsed = usedSourceHashes.size > 0 && usedSourceHashes.has(snippet)
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
                      <div className="mt-2 flex items-center gap-3 text-[10px] text-[var(--text-faint)] flex-wrap">
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
                        {src.source_sheet && (
                          <span className="rounded bg-violet-500/20 text-violet-300 px-1.5 py-0.5">{src.source_sheet}</span>
                        )}
                        {src.match_score != null && (
                          <span className="flex items-center gap-1 text-amber-400">
                            <Star size={10} /> {src.match_score}% match
                            {src.topic_score != null && (
                              <span className="text-[9px] text-amber-400/70 ml-1">
                                T:{src.topic_score} M:{src.mechanics_score} A:{src.audience_score}
                              </span>
                            )}
                          </span>
                        )}
                        {src.match_reason && (
                          <span className="basis-full text-[10px] text-amber-400/60 italic mt-0.5">{src.match_reason}</span>
                        )}
                        {isUsed && (
                          <span className="rounded bg-orange-500/20 text-orange-400 px-1.5 py-0.5 font-medium">Already Used</span>
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

            {/* Pagination */}
            {viralTotal > 20 && (
              <div className="flex items-center justify-between border-t border-[var(--border-2)] px-5 py-2.5 text-[11px]">
                <span className="text-[var(--text-faint)]">
                  Page {vpPage} of {Math.ceil(viralTotal / 20)} · {viralTotal} posts
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setVpPage(p => Math.max(1, p - 1))}
                    disabled={vpPage <= 1}
                    className="rounded px-2.5 py-1 text-[var(--text-muted)] disabled:opacity-30 hover:bg-[var(--surface-3)]"
                  >Prev</button>
                  <button
                    onClick={() => setVpPage(p => p + 1)}
                    disabled={vpPage >= Math.ceil(viralTotal / 20)}
                    className="rounded px-2.5 py-1 text-[var(--text-muted)] disabled:opacity-30 hover:bg-[var(--surface-3)]"
                  >Next</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Schedule modal */}
      {showScheduleModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setShowScheduleModal(false)} />
          <div className="relative w-full max-w-sm animate-scale-in rounded-2xl border border-[var(--border-1)] bg-[var(--surface-2)] p-5 shadow-[var(--shadow-overlay)]">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2 text-[14px] font-semibold text-[var(--text-primary)]">
                <Clock size={14} /> Schedule Generation
              </div>
              <button onClick={() => setShowScheduleModal(false)} className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--text-muted)] hover:bg-[var(--surface-3)]">
                <X size={15} />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Time (IST)</label>
                <div className="flex items-center gap-1">
                  <input type="number" min={0} max={23} value={schedHour} onChange={e => setSchedHour(Number(e.target.value))} className="field w-16 text-[12px] text-center" />
                  <span className="text-[var(--text-muted)]">:</span>
                  <input type="number" min={0} max={59} step={15} value={schedMinute} onChange={e => setSchedMinute(Number(e.target.value))} className="field w-16 text-[12px] text-center" />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Days</label>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].map(d => (
                    <button
                      key={d}
                      onClick={() => setSchedDays(prev => prev.includes(d) ? prev.filter(x => x !== d) : [...prev, d])}
                      className={clsx(
                        'rounded-md px-2 py-1 text-[10px] font-medium uppercase transition-colors',
                        schedDays.includes(d)
                          ? 'bg-white text-black'
                          : 'bg-[var(--surface-3)] text-[var(--text-faint)]',
                      )}
                    >{d}</button>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-[var(--border-2)] bg-[var(--surface-3)] p-2.5 text-[11px] text-[var(--text-muted)]">
                <p>{active} · {nSources} sources × {postsPerSource} posts · {effort} effort · creativity {creativity}</p>
              </div>

              <div className="flex gap-2">
                <Button variant="primary" className="flex-1" onClick={createSchedule} disabled={savingSchedule || schedDays.length === 0} loading={savingSchedule}>
                  Create Schedule
                </Button>
                <Button variant="ghost" onClick={() => setShowScheduleModal(false)}>Cancel</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
