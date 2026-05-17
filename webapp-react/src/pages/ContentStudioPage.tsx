import { useState, useEffect, useCallback, useRef } from 'react'
import {
  PenTool, Search, Sparkles, FileText, Mic, Loader2,
  Trash2, ChevronDown, ChevronRight, Check, X, Clock, Upload,
  FolderPlus, Video, ClipboardPaste, Plus, FolderOpen,
} from 'lucide-react'
import { apiGet, apiPost, apiDelete, apiPut, apiUploadWithFields } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'

// ── Types ────────────────────────────────────────────────────────────────

interface BlogTopic {
  topic: string
  relevance_score: number
  source: string
  supporting_beliefs: string[]
  trending_signal: string
  suggested_angles: string[]
}

interface NarrativeAngle {
  angle: string
  format_recommendation: string
  headline_draft?: string
  supporting_transcript_quotes: string[]
  confidence: number
  rationale?: string
}

interface BlogMeta {
  blog_id: string
  founder_slug: string
  title: string
  topic: string
  tone: string
  format_type: string
  source_type: string
  word_count: number
  voice_score: number
  created_at: string
  status: string
}

interface TaskStatus {
  task_id: string
  status: string
  progress: number
  stage: string
  error: string | null
  blog_id: string | null
  result: any
  log: { stage: string; status: string; data?: any }[]
  log_offset?: number
}

interface Podcast {
  podcast_id: string
  founder_slug: string
  title: string
  host: string
  episode_url: string
  source_type: string
  youtube_url: string
  transcript_length: number
  date: string
  created_at: string
}

interface DocCategory {
  category_id: string
  founder_slug: string
  name: string
  description: string
  created_at: string
}

interface StudioDocument {
  document_id: string
  founder_slug: string
  category_id: string | null
  filename: string
  file_type: string
  file_size: number
  text_length: number
  created_at: string
}

// ── Helpers ──────────────────────────────────────────────────────────────

const TONES = ['conversational', 'formal', 'provocative', 'educational'] as const
const FORMATS = [
  { value: 'thought_leadership', label: 'Thought Leadership' },
  { value: 'behind_the_scenes', label: 'Behind the Scenes' },
  { value: 'listicle', label: 'Listicle' },
  { value: 'how_to', label: 'How-To Guide' },
] as const

function scoreBadge(score: number) {
  const color = score >= 0.8 ? 'var(--success)' : score >= 0.5 ? 'var(--warning, #f59e0b)' : 'var(--text-muted)'
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold"
      style={{ background: `color-mix(in srgb, ${color} 15%, transparent)`, color }}
    >
      {(score * 100).toFixed(0)}%
    </span>
  )
}

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    draft: 'var(--text-muted)',
    published: 'var(--success)',
    archived: 'var(--warning, #f59e0b)',
  }
  const c = colors[status] || 'var(--text-muted)'
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
      style={{ background: `color-mix(in srgb, ${c} 15%, transparent)`, color: c }}
    >
      {status}
    </span>
  )
}

function sourceBadge(type: string) {
  const colors: Record<string, string> = { upload: 'var(--text-muted)', youtube: '#ef4444', paste: 'var(--text-secondary)' }
  const c = colors[type] || 'var(--text-muted)'
  return (
    <span className="rounded bg-[var(--surface-4)] px-1.5 py-0.5 text-[10px] font-medium" style={{ color: c }}>
      {type}
    </span>
  )
}

// ── Main Page ────────────────────────────────────────────────────────────

export default function ContentStudioPage() {
  const [tab, setTab] = useState<'blogs' | 'narrative' | 'podcasts' | 'documents' | 'history'>('blogs')

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--surface-3)]">
          <PenTool size={18} className="text-[var(--text-secondary)]" />
        </div>
        <div>
          <h1 className="font-[var(--font-display)] text-[20px] font-bold text-[var(--text-primary)]">
            Content Studio
          </h1>
          <p className="text-[12px] text-[var(--text-muted)]">
            Generate long-form blog posts in your founder's voice
          </p>
        </div>
      </div>

      <div className="flex gap-1 rounded-xl bg-[var(--surface-2)] p-1">
        {([
          { id: 'blogs' as const, label: 'Blogs', icon: FileText },
          { id: 'narrative' as const, label: 'Narrative', icon: Mic },
          { id: 'podcasts' as const, label: 'Podcasts', icon: Mic },
          { id: 'documents' as const, label: 'Documents', icon: FolderOpen },
          { id: 'history' as const, label: 'History', icon: Clock },
        ]).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-[12px] font-medium transition-all ${
              tab === id
                ? 'bg-[var(--surface-4)] text-[var(--text-primary)] shadow-sm'
                : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
            }`}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      {tab === 'blogs' && <BlogsTab />}
      {tab === 'narrative' && <NarrativeTab />}
      {tab === 'podcasts' && <PodcastsTab />}
      {tab === 'documents' && <DocumentsTab />}
      {tab === 'history' && <HistoryTab />}
    </div>
  )
}

// ── Blogs Tab ────────────────────────────────────────────────────────────

function BlogsTab() {
  const founder = useFounderStore(s => s.active)
  const [topics, setTopics] = useState<BlogTopic[]>([])
  const [discovering, setDiscovering] = useState(false)
  const [customTopic, setCustomTopic] = useState('')
  const [selectedTopic, setSelectedTopic] = useState('')
  const [tone, setTone] = useState<string>('conversational')
  const [wordCount, setWordCount] = useState(1500)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null)
  const [generating, setGenerating] = useState(false)

  // v2: mode, instructions, source selection
  const [mode, setMode] = useState<'auto' | 'instructed'>('auto')
  const [instructions, setInstructions] = useState('')
  const [podcasts, setPodcasts] = useState<Podcast[]>([])
  const [, setCategories] = useState<DocCategory[]>([])
  const [documents, setDocuments] = useState<StudioDocument[]>([])
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([])
  const [selectedPodIds, setSelectedPodIds] = useState<string[]>([])

  useEffect(() => {
    apiGet<{ podcasts: Podcast[] }>(`/api/studio/podcasts/${founder}`).then(r => setPodcasts(r.podcasts || [])).catch(() => {})
    apiGet<{ categories: DocCategory[] }>(`/api/studio/categories/${founder}`).then(r => setCategories(r.categories || [])).catch(() => {})
    apiGet<{ documents: StudioDocument[] }>(`/api/studio/documents/${founder}`).then(r => setDocuments(r.documents || [])).catch(() => {})
  }, [founder])

  const discoverTopics = async () => {
    setDiscovering(true)
    try {
      const res = await apiPost<{ topics: BlogTopic[] }>('/api/blog/discover-topics', {
        founder_slug: founder,
        n_topics: 10,
      })
      setTopics(res.topics || [])
      if (res.topics?.length) setSelectedTopic(res.topics[0].topic)
    } catch (e) {
      console.error('Topic discovery failed:', e)
    } finally {
      setDiscovering(false)
    }
  }

  const startGeneration = async () => {
    const topic = customTopic || selectedTopic
    if (!topic && mode !== 'instructed') return
    if (mode === 'instructed' && !instructions && !topic) return
    setGenerating(true)
    setTaskStatus(null)
    try {
      const res = await apiPost<{ task_id: string }>('/api/blog/generate/background', {
        founder_slug: founder,
        topic: topic || instructions.slice(0, 100),
        tone,
        target_word_count: wordCount,
        seo_focus: true,
        custom_instructions: instructions,
        document_ids: selectedDocIds,
        podcast_ids: selectedPodIds,
        mode,
      })
      setTaskId(res.task_id)
    } catch (e) {
      console.error('Generation failed:', e)
      setGenerating(false)
    }
  }

  useEffect(() => {
    if (!taskId) return
    let logOffset = 0
    const interval = setInterval(async () => {
      try {
        const status = await apiGet<TaskStatus>(`/api/blog/generate/status/${taskId}?since=${logOffset}`)
        setTaskStatus(prev => ({
          ...status,
          log: [...(prev?.log || []), ...status.log],
        }))
        logOffset = status.log_offset ?? logOffset
        if (['done', 'error', 'cancelled'].includes(status.status)) {
          clearInterval(interval)
          setGenerating(false)
        }
      } catch {
        clearInterval(interval)
        setGenerating(false)
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [taskId])

  const toggleDocId = (id: string) => setSelectedDocIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  const togglePodId = (id: string) => setSelectedPodIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  return (
    <div className="space-y-5">
      {/* Mode Toggle */}
      <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
        <div className="mb-4 flex items-center gap-3">
          <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">Generation Mode</h2>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setMode('auto')}
            className={`flex-1 rounded-lg px-4 py-3 text-[13px] font-medium transition-all ${
              mode === 'auto' ? 'bg-white text-black' : 'bg-[var(--surface-3)] text-[var(--text-secondary)] hover:bg-[var(--surface-4)]'
            }`}
          >
            <Sparkles size={14} className="mr-2 inline" />
            Let us write
            <p className="mt-1 text-[11px] font-normal opacity-70">AI discovers topics and writes the blog</p>
          </button>
          <button
            onClick={() => setMode('instructed')}
            className={`flex-1 rounded-lg px-4 py-3 text-[13px] font-medium transition-all ${
              mode === 'instructed' ? 'bg-white text-black' : 'bg-[var(--surface-3)] text-[var(--text-secondary)] hover:bg-[var(--surface-4)]'
            }`}
          >
            <PenTool size={14} className="mr-2 inline" />
            Provide instructions
            <p className="mt-1 text-[11px] font-normal opacity-70">Tell us what you want written</p>
          </button>
        </div>
      </div>

      {/* Custom Instructions (instructed mode) */}
      {mode === 'instructed' && (
        <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
          <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
            Instructions
          </label>
          <textarea
            value={instructions}
            onChange={e => setInstructions(e.target.value)}
            placeholder="Describe what kind of blog post you want. E.g., 'Write a technical deep-dive about our Series B fundraising strategy, focusing on the contrarian approach we took...'"
            className="field w-full resize-none"
            rows={4}
          />
        </div>
      )}

      {/* Topic Discovery (auto mode) */}
      {mode === 'auto' && (
        <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">
              <Search size={14} className="mr-2 inline text-[var(--text-muted)]" />
              Topic Discovery
            </h2>
            <button
              onClick={discoverTopics}
              disabled={discovering}
              className="flex items-center gap-2 rounded-lg bg-[var(--surface-3)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-4)] disabled:opacity-40"
            >
              {discovering ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
              {discovering ? 'Discovering...' : 'Find Topics'}
            </button>
          </div>

          {topics.length > 0 && (
            <div className="mb-4 grid gap-2 sm:grid-cols-2">
              {topics.slice(0, 6).map((t, i) => (
                <button
                  key={i}
                  onClick={() => { setSelectedTopic(t.topic); setCustomTopic('') }}
                  className={`rounded-xl border p-3 text-left transition-all ${
                    selectedTopic === t.topic && !customTopic
                      ? 'border-white/30 bg-[var(--surface-3)]'
                      : 'border-[var(--border-2)] hover:border-[var(--border-1)] hover:bg-[var(--surface-2)]'
                  }`}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-[13px] font-medium text-[var(--text-primary)]">{t.topic}</span>
                    {scoreBadge(t.relevance_score)}
                  </div>
                  {t.trending_signal && (
                    <p className="text-[11px] text-[var(--text-muted)]">{t.trending_signal}</p>
                  )}
                </button>
              ))}
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
              Or enter a custom topic
            </label>
            <input
              type="text"
              value={customTopic}
              onChange={e => { setCustomTopic(e.target.value); if (e.target.value) setSelectedTopic('') }}
              placeholder="e.g. Why most hiring processes are broken"
              className="field w-full"
            />
          </div>
        </div>
      )}

      {/* Source Material Selection */}
      {(documents.length > 0 || podcasts.length > 0) && (
        <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
          <h2 className="mb-4 text-[14px] font-semibold text-[var(--text-primary)]">
            <FolderOpen size={14} className="mr-2 inline text-[var(--text-muted)]" />
            Source Material (optional)
          </h2>

          {documents.length > 0 && (
            <div className="mb-3">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Documents</p>
              <div className="flex flex-wrap gap-1.5">
                {documents.map(d => (
                  <button
                    key={d.document_id}
                    onClick={() => toggleDocId(d.document_id)}
                    className={`rounded-lg px-3 py-1.5 text-[11px] font-medium transition-all ${
                      selectedDocIds.includes(d.document_id)
                        ? 'bg-white text-black'
                        : 'bg-[var(--surface-3)] text-[var(--text-secondary)] hover:bg-[var(--surface-4)]'
                    }`}
                  >
                    {d.filename}
                  </button>
                ))}
              </div>
            </div>
          )}

          {podcasts.length > 0 && (
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Podcasts</p>
              <div className="flex flex-wrap gap-1.5">
                {podcasts.map(p => (
                  <button
                    key={p.podcast_id}
                    onClick={() => togglePodId(p.podcast_id)}
                    className={`rounded-lg px-3 py-1.5 text-[11px] font-medium transition-all ${
                      selectedPodIds.includes(p.podcast_id)
                        ? 'bg-white text-black'
                        : 'bg-[var(--surface-3)] text-[var(--text-secondary)] hover:bg-[var(--surface-4)]'
                    }`}
                  >
                    {p.title}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Generation Controls */}
      <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
        <h2 className="mb-4 text-[14px] font-semibold text-[var(--text-primary)]">
          <Sparkles size={14} className="mr-2 inline text-[var(--text-muted)]" />
          Generate Blog
        </h2>

        <div className="mb-4 grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
              Tone
            </label>
            <div className="flex flex-wrap gap-1.5">
              {TONES.map(t => (
                <button
                  key={t}
                  onClick={() => setTone(t)}
                  className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition-all ${
                    tone === t
                      ? 'bg-white text-black'
                      : 'bg-[var(--surface-3)] text-[var(--text-secondary)] hover:bg-[var(--surface-4)]'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
              Target length: {wordCount} words
            </label>
            <input
              type="range"
              min={800}
              max={3000}
              step={100}
              value={wordCount}
              onChange={e => setWordCount(Number(e.target.value))}
              className="w-full accent-white"
            />
            <div className="mt-1 flex justify-between text-[10px] text-[var(--text-muted)]">
              <span>800</span>
              <span>3000</span>
            </div>
          </div>
        </div>

        <button
          onClick={startGeneration}
          disabled={generating || (mode === 'auto' && !customTopic && !selectedTopic) || (mode === 'instructed' && !instructions && !customTopic && !selectedTopic)}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 text-[13px] font-semibold text-black transition-all hover:bg-white/90 disabled:opacity-40"
        >
          {generating ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
          {generating ? 'Generating...' : 'Generate Blog Post'}
        </button>
      </div>

      {taskStatus && <PipelineProgress status={taskStatus} />}
      {taskStatus?.status === 'done' && taskStatus.result && (
        <BlogResult result={taskStatus.result} blogId={taskStatus.blog_id} />
      )}
    </div>
  )
}

// ── Narrative Tab ────────────────────────────────────────────────────────

function NarrativeTab() {
  const founder = useFounderStore(s => s.active)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<any>(null)
  const [angles, setAngles] = useState<NarrativeAngle[]>([])
  const [selectedAngles, setSelectedAngles] = useState<Set<string>>(new Set())
  const [customAngle, setCustomAngle] = useState('')
  const [format, setFormat] = useState('thought_leadership')
  const [tone, setTone] = useState('conversational')
  const [wordCount, setWordCount] = useState(1500)
  const [useFounderVoice, setUseFounderVoice] = useState(true)
  const [customInstructions, setCustomInstructions] = useState('')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null)
  const [generating, setGenerating] = useState(false)

  const [podcasts, setPodcasts] = useState<Podcast[]>([])
  const [selectedPodIds, setSelectedPodIds] = useState<string[]>([])

  useEffect(() => {
    apiGet<{ podcasts: Podcast[] }>(`/api/studio/podcasts/${founder}`).then(r => setPodcasts(r.podcasts || [])).catch(() => {})
  }, [founder])

  const toggleAngle = (angle: string) => {
    setSelectedAngles(prev => {
      const next = new Set(prev)
      if (next.has(angle)) next.delete(angle); else next.add(angle)
      return next
    })
  }

  const analyzeTranscripts = async () => {
    setAnalyzing(true)
    try {
      const res = await apiPost<{ angles: NarrativeAngle[]; analysis: any; transcript_length: number }>(
        '/api/blog/narrative/analyze',
        { founder_slug: founder, podcast_ids: selectedPodIds },
      )
      if ((res as any).error) {
        alert((res as any).error)
        return
      }
      setAnalysis(res.analysis)
      setAngles(res.angles || [])
      setSelectedAngles(new Set())
      setCustomAngle('')
    } catch (e) {
      console.error('Analysis failed:', e)
    } finally {
      setAnalyzing(false)
    }
  }

  const canGenerate = selectedAngles.size > 0 || customAngle.trim().length > 0

  const startGeneration = async () => {
    if (!canGenerate) return
    const anglesList = Array.from(selectedAngles)
    const primaryAngle = customAngle.trim() || anglesList[0] || ''
    const additionalAngles = customAngle.trim()
      ? anglesList
      : anglesList.slice(1)

    setGenerating(true)
    setTaskStatus(null)
    try {
      const res = await apiPost<{ task_id: string }>('/api/blog/narrative/generate/background', {
        founder_slug: founder,
        narrative_angle: primaryAngle,
        narrative_angles: additionalAngles,
        format_type: format,
        tone,
        target_word_count: wordCount,
        podcast_ids: selectedPodIds,
        use_founder_voice: useFounderVoice,
        custom_instructions: customInstructions,
      })
      setTaskId(res.task_id)
    } catch (e) {
      console.error('Generation failed:', e)
      setGenerating(false)
    }
  }

  useEffect(() => {
    if (!taskId) return
    let logOffset = 0
    const interval = setInterval(async () => {
      try {
        const status = await apiGet<TaskStatus>(`/api/blog/generate/status/${taskId}?since=${logOffset}`)
        setTaskStatus(prev => ({
          ...status,
          log: [...(prev?.log || []), ...status.log],
        }))
        logOffset = status.log_offset ?? logOffset
        if (['done', 'error', 'cancelled'].includes(status.status)) {
          clearInterval(interval)
          setGenerating(false)
        }
      } catch {
        clearInterval(interval)
        setGenerating(false)
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [taskId])

  return (
    <div className="space-y-5">
      {/* Podcast Selection */}
      {podcasts.length > 0 && (
        <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
            Select Podcasts to Analyze
          </p>
          <div className="flex flex-wrap gap-1.5">
            {podcasts.map(p => (
              <button
                key={p.podcast_id}
                onClick={() => setSelectedPodIds(prev => prev.includes(p.podcast_id) ? prev.filter(x => x !== p.podcast_id) : [...prev, p.podcast_id])}
                className={`rounded-lg px-3 py-1.5 text-[11px] font-medium transition-all ${
                  selectedPodIds.includes(p.podcast_id)
                    ? 'bg-white text-black'
                    : 'bg-[var(--surface-3)] text-[var(--text-secondary)] hover:bg-[var(--surface-4)]'
                }`}
              >
                <Mic size={11} className="mr-1 inline" />
                {p.title}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Transcript Analysis */}
      <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">
            <Mic size={14} className="mr-2 inline text-[var(--text-muted)]" />
            Transcript Analysis
          </h2>
          <button
            onClick={analyzeTranscripts}
            disabled={analyzing}
            className="flex items-center gap-2 rounded-lg bg-[var(--surface-3)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-4)] disabled:opacity-40"
          >
            {analyzing ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
            {analyzing ? 'Analyzing...' : 'Analyze Transcripts'}
          </button>
        </div>

        {analysis && (
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-[var(--surface-2)] p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Themes</p>
              <p className="text-[18px] font-bold text-[var(--text-primary)]">{analysis.themes?.length || 0}</p>
            </div>
            <div className="rounded-xl bg-[var(--surface-2)] p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Quotes</p>
              <p className="text-[18px] font-bold text-[var(--text-primary)]">{analysis.quotes?.length || 0}</p>
            </div>
            <div className="rounded-xl bg-[var(--surface-2)] p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">Stories</p>
              <p className="text-[18px] font-bold text-[var(--text-primary)]">{analysis.stories?.length || 0}</p>
            </div>
          </div>
        )}

        {analysis && angles.length === 0 && (
          <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/5 p-3">
            <p className="text-[12px] text-yellow-400">
              No narrative angles found. The transcript may be too short, or analysis output was truncated. Try selecting a different transcript or try again.
            </p>
          </div>
        )}

        {angles.length > 0 && (
          <div className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
              Narrative Angles (select one or more)
            </p>
            {angles.slice(0, 6).map((a, i) => {
              const isSelected = selectedAngles.has(a.angle)
              return (
                <button
                  key={i}
                  onClick={() => toggleAngle(a.angle)}
                  className={`w-full rounded-xl border p-3 text-left transition-all ${
                    isSelected
                      ? 'border-white/30 bg-[var(--surface-3)]'
                      : 'border-[var(--border-2)] hover:border-[var(--border-1)] hover:bg-[var(--surface-2)]'
                  }`}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <div className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-all ${
                      isSelected ? 'border-white bg-white' : 'border-[var(--text-muted)]'
                    }`}>
                      {isSelected && <Check size={10} className="text-black" />}
                    </div>
                    <span className="text-[13px] font-medium text-[var(--text-primary)]">{a.angle}</span>
                    {scoreBadge(a.confidence)}
                  </div>
                  {a.headline_draft && (
                    <p className="ml-6 text-[11px] italic text-[var(--text-secondary)]">{a.headline_draft}</p>
                  )}
                  {a.rationale && (
                    <p className="ml-6 mt-1 text-[11px] text-[var(--text-muted)]">{a.rationale}</p>
                  )}
                  <div className="ml-6 mt-1 flex items-center gap-2">
                    <span className="rounded bg-[var(--surface-4)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
                      {a.format_recommendation}
                    </span>
                    {a.supporting_transcript_quotes?.length > 0 && (
                      <span className="text-[10px] text-[var(--text-muted)]">
                        {a.supporting_transcript_quotes.length} quote{a.supporting_transcript_quotes.length > 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        )}

        {/* Custom Narrative Direction */}
        <div className="mt-4">
          <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
            Custom Narrative Direction
          </label>
          <textarea
            value={customAngle}
            onChange={e => setCustomAngle(e.target.value)}
            placeholder="Write your own angle or refine selected ones. E.g., 'Compare the coaching industry in India vs US, focusing on the IIT admissions angle...'"
            className="field w-full resize-none"
            rows={3}
          />
        </div>
      </div>

      {/* Generation Controls — visible when angles selected or custom angle entered */}
      {canGenerate && (
        <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
          <h2 className="mb-4 text-[14px] font-semibold text-[var(--text-primary)]">
            <Sparkles size={14} className="mr-2 inline text-[var(--text-muted)]" />
            Generate from Narrative
          </h2>

          {/* Selected angles summary */}
          {selectedAngles.size > 0 && (
            <div className="mb-4">
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Selected Angles ({selectedAngles.size})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {Array.from(selectedAngles).map(a => (
                  <span key={a} className="flex items-center gap-1 rounded-lg bg-white/10 px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
                    {a.length > 60 ? a.slice(0, 60) + '...' : a}
                    <button onClick={() => toggleAngle(a)} className="ml-1 text-[var(--text-muted)] hover:text-[var(--text-primary)]">
                      <X size={10} />
                    </button>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Founder Voice Toggle */}
          <div className="mb-4 flex items-center justify-between rounded-xl bg-[var(--surface-2)] p-3">
            <div>
              <p className="text-[13px] font-medium text-[var(--text-primary)]">Founder Voice</p>
              <p className="text-[11px] text-[var(--text-muted)]">
                {useFounderVoice
                  ? 'Blog will use founder voice markers, beliefs & stories'
                  : 'Pure podcast content — no founder voice overlay'}
              </p>
            </div>
            <button
              onClick={() => setUseFounderVoice(v => !v)}
              className={`relative h-6 w-11 rounded-full transition-colors ${
                useFounderVoice ? 'bg-white' : 'bg-[var(--surface-4)]'
              }`}
            >
              <span className={`absolute top-0.5 h-5 w-5 rounded-full transition-all ${
                useFounderVoice
                  ? 'left-[22px] bg-black'
                  : 'left-0.5 bg-[var(--text-muted)]'
              }`} />
            </button>
          </div>

          {/* Format & Tone */}
          <div className="mb-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Format
              </label>
              <div className="flex flex-wrap gap-1.5">
                {FORMATS.map(f => (
                  <button
                    key={f.value}
                    onClick={() => setFormat(f.value)}
                    className={`rounded-lg px-3 py-1.5 text-[11px] font-medium transition-all ${
                      format === f.value
                        ? 'bg-white text-black'
                        : 'bg-[var(--surface-3)] text-[var(--text-secondary)] hover:bg-[var(--surface-4)]'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Tone
              </label>
              <div className="flex flex-wrap gap-1.5">
                {TONES.map(t => (
                  <button
                    key={t}
                    onClick={() => setTone(t)}
                    className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition-all ${
                      tone === t
                        ? 'bg-white text-black'
                        : 'bg-[var(--surface-3)] text-[var(--text-secondary)] hover:bg-[var(--surface-4)]'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Word Count */}
          <div className="mb-4">
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
              Target length: {wordCount} words
            </label>
            <input
              type="range"
              min={800}
              max={3000}
              step={100}
              value={wordCount}
              onChange={e => setWordCount(Number(e.target.value))}
              className="w-full accent-white"
            />
            <div className="mt-1 flex justify-between text-[10px] text-[var(--text-muted)]">
              <span>800</span>
              <span>3000</span>
            </div>
          </div>

          {/* Custom Instructions */}
          <div className="mb-4">
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
              Additional Instructions (optional)
            </label>
            <textarea
              value={customInstructions}
              onChange={e => setCustomInstructions(e.target.value)}
              placeholder="E.g., 'Focus on the comparison between Indian and US education systems' or 'Include specific data points about market size'"
              className="field w-full resize-none"
              rows={3}
            />
          </div>

          <button
            onClick={startGeneration}
            disabled={generating}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 text-[13px] font-semibold text-black transition-all hover:bg-white/90 disabled:opacity-40"
          >
            {generating ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            {generating ? 'Generating...' : 'Generate Blog Post'}
          </button>
        </div>
      )}

      {taskStatus && <PipelineProgress status={taskStatus} />}
      {taskStatus?.status === 'done' && taskStatus.result && (
        <BlogResult result={taskStatus.result} blogId={taskStatus.blog_id} />
      )}
    </div>
  )
}

// ── Podcasts Tab ─────────────────────────────────────────────────────────

function PodcastsTab() {
  const founder = useFounderStore(s => s.active)
  const [podcasts, setPodcasts] = useState<Podcast[]>([])
  const [loading, setLoading] = useState(true)
  const [uploadMode, setUploadMode] = useState<'file' | 'youtube' | 'paste'>('file')
  const [uploading, setUploading] = useState(false)

  // Form fields
  const [title, setTitle] = useState('')
  const [host, setHost] = useState('')
  const [date, setDate] = useState('')
  const [episodeUrl, setEpisodeUrl] = useState('')
  const [youtubeUrl, setYoutubeUrl] = useState('')
  const [pasteText, setPasteText] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const loadPodcasts = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiGet<{ podcasts: Podcast[] }>(`/api/studio/podcasts/${founder}`)
      setPodcasts(res.podcasts || [])
    } catch {
    } finally {
      setLoading(false)
    }
  }, [founder])

  useEffect(() => { loadPodcasts() }, [loadPodcasts])

  const resetForm = () => {
    setTitle(''); setHost(''); setDate(''); setEpisodeUrl(''); setYoutubeUrl(''); setPasteText('')
    if (fileRef.current) fileRef.current.value = ''
  }

  const handleUpload = async () => {
    setUploading(true)
    try {
      if (uploadMode === 'file') {
        const file = fileRef.current?.files?.[0]
        if (!file) { alert('Select a file'); return }
        await apiUploadWithFields('/api/studio/podcasts/upload', file, {
          founder_slug: founder, title, host, date, episode_url: episodeUrl,
        })
      } else if (uploadMode === 'youtube') {
        if (!youtubeUrl) { alert('Enter a YouTube URL'); return }
        await apiPost('/api/studio/podcasts/youtube', {
          founder_slug: founder, youtube_url: youtubeUrl, title, host, date,
        })
      } else {
        if (!pasteText.trim()) { alert('Paste transcript text'); return }
        await apiPost('/api/studio/podcasts/paste', {
          founder_slug: founder, text: pasteText, title: title || 'Pasted Transcript', host, date,
        })
      }
      resetForm()
      await loadPodcasts()
    } catch (e: any) {
      alert(e.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const deletePodcast = async (id: string) => {
    if (!confirm('Delete this podcast transcript?')) return
    try {
      await apiDelete(`/api/studio/podcasts/${id}`)
      setPodcasts(prev => prev.filter(p => p.podcast_id !== id))
    } catch {}
  }

  return (
    <div className="space-y-5">
      {/* Upload Form */}
      <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
        <h2 className="mb-4 text-[14px] font-semibold text-[var(--text-primary)]">
          <Plus size={14} className="mr-2 inline text-[var(--text-muted)]" />
          Add Podcast Transcript
        </h2>

        <div className="mb-4 flex gap-1.5">
          {([
            { id: 'file' as const, label: 'Upload File', icon: Upload },
            { id: 'youtube' as const, label: 'YouTube', icon: Video },
            { id: 'paste' as const, label: 'Paste Text', icon: ClipboardPaste },
          ]).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setUploadMode(id)}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-all ${
                uploadMode === id
                  ? 'bg-white text-black'
                  : 'bg-[var(--surface-3)] text-[var(--text-secondary)] hover:bg-[var(--surface-4)]'
              }`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Title</label>
              <input type="text" value={title} onChange={e => setTitle(e.target.value)} placeholder="Episode title" className="field w-full" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Host</label>
              <input type="text" value={host} onChange={e => setHost(e.target.value)} placeholder="Host name" className="field w-full" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Date</label>
              <input type="date" value={date} onChange={e => setDate(e.target.value)} className="field w-full" />
            </div>
            {uploadMode === 'file' && (
              <div>
                <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Episode URL</label>
                <input type="url" value={episodeUrl} onChange={e => setEpisodeUrl(e.target.value)} placeholder="https://..." className="field w-full" />
              </div>
            )}
          </div>

          {uploadMode === 'file' && (
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Transcript File</label>
              <input ref={fileRef} type="file" accept=".txt,.md,.docx" className="field w-full text-[12px]" />
            </div>
          )}

          {uploadMode === 'youtube' && (
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">YouTube URL</label>
              <input type="url" value={youtubeUrl} onChange={e => setYoutubeUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=..." className="field w-full" />
            </div>
          )}

          {uploadMode === 'paste' && (
            <div>
              <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Transcript Text</label>
              <textarea value={pasteText} onChange={e => setPasteText(e.target.value)} placeholder="Paste the full transcript here..." className="field w-full resize-none" rows={6} />
            </div>
          )}

          <button
            onClick={handleUpload}
            disabled={uploading}
            className="flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-[13px] font-semibold text-black transition-all hover:bg-white/90 disabled:opacity-40"
          >
            {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
            {uploading ? (uploadMode === 'youtube' ? 'Extracting...' : 'Uploading...') : (uploadMode === 'youtube' ? 'Extract Transcript' : 'Add Transcript')}
          </button>
        </div>
      </div>

      {/* Podcast List */}
      <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
        <h2 className="mb-4 text-[14px] font-semibold text-[var(--text-primary)]">
          <Mic size={14} className="mr-2 inline text-[var(--text-muted)]" />
          Podcast Library
        </h2>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={18} className="animate-spin text-[var(--text-muted)]" />
          </div>
        ) : podcasts.length === 0 ? (
          <p className="py-4 text-center text-[13px] text-[var(--text-muted)]">No podcasts added yet</p>
        ) : (
          <div className="space-y-2">
            {podcasts.map(p => (
              <PodcastRow key={p.podcast_id} podcast={p} onDelete={deletePodcast} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function PodcastRow({ podcast: p, onDelete }: { podcast: Podcast; onDelete: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false)
  const [transcript, setTranscript] = useState<{ text: string; structured: any } | null>(null)
  const [loadingTranscript, setLoadingTranscript] = useState(false)

  const toggleTranscript = async () => {
    if (expanded) { setExpanded(false); return }
    if (transcript) { setExpanded(true); return }
    setLoadingTranscript(true)
    try {
      const res = await apiGet<{ text: string; structured: any }>(`/api/studio/podcasts/${p.podcast_id}/transcript`)
      setTranscript(res)
      setExpanded(true)
    } catch (e) {
      console.error('Failed to load transcript:', e)
    } finally {
      setLoadingTranscript(false)
    }
  }

  const structured = transcript?.structured
  const segments = structured?.segments || []

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border-2)]">
      <div className="flex items-center gap-3 p-3">
        <button onClick={toggleTranscript} className="text-[var(--text-muted)]">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <div className="min-w-0 flex-1 cursor-pointer" onClick={toggleTranscript}>
          <p className="truncate text-[13px] font-medium text-[var(--text-primary)]">{p.title}</p>
          <div className="mt-1 flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
            {p.host && <span>{p.host}</span>}
            {p.host && p.date && <span>·</span>}
            {p.date && <span>{p.date}</span>}
            <span>·</span>
            <span>{(p.transcript_length / 1000).toFixed(1)}k chars</span>
            {structured && <span>· {segments.length} segments</span>}
          </div>
        </div>
        {sourceBadge(p.source_type)}
        {loadingTranscript && <Loader2 size={13} className="animate-spin text-[var(--text-muted)]" />}
        <button
          onClick={() => onDelete(p.podcast_id)}
          className="rounded-lg p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--error, #ef4444)]"
        >
          <Trash2 size={13} />
        </button>
      </div>

      {expanded && transcript && (
        <div className="border-t border-[var(--border-2)] bg-[var(--surface-2)] p-4">
          {structured?.summary && (
            <div className="mb-3 rounded-lg bg-[var(--surface-3)] p-3">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Summary</p>
              <p className="text-[12px] leading-relaxed text-[var(--text-secondary)]">{structured.summary}</p>
            </div>
          )}
          {structured?.speakers?.length > 0 && (
            <div className="mb-3 flex items-center gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Speakers:</span>
              {structured.speakers.map((s: string, i: number) => (
                <span key={i} className="rounded bg-[var(--surface-4)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]">{s}</span>
              ))}
            </div>
          )}
          {segments.length > 0 ? (
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {segments.map((seg: any, i: number) => (
                <div key={i} className="rounded-lg bg-[var(--surface-1)] p-3">
                  <div className="mb-1 flex items-center gap-2">
                    {seg.speaker && <span className="text-[11px] font-semibold text-[var(--text-primary)]">{seg.speaker}</span>}
                    {seg.topic && <span className="rounded bg-[var(--surface-4)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">{seg.topic}</span>}
                  </div>
                  <p className="text-[12px] leading-relaxed text-[var(--text-secondary)]">{seg.text}</p>
                </div>
              ))}
            </div>
          ) : (
            <pre className="max-h-[400px] overflow-y-auto whitespace-pre-wrap text-[12px] leading-relaxed text-[var(--text-secondary)]">
              {transcript.text}
            </pre>
          )}
          {structured?.key_quotes?.length > 0 && (
            <div className="mt-3">
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Key Quotes</p>
              <div className="space-y-1">
                {structured.key_quotes.map((q: string, i: number) => (
                  <p key={i} className="border-l-2 border-[var(--text-muted)] pl-3 text-[12px] italic text-[var(--text-secondary)]">"{q}"</p>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Documents Tab ────────────────────────────────────────────────────────

function DocumentsTab() {
  const founder = useFounderStore(s => s.active)
  const [categories, setCategories] = useState<DocCategory[]>([])
  const [documents, setDocuments] = useState<StudioDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [newCatName, setNewCatName] = useState('')
  const [selectedCat, setSelectedCat] = useState<string>('')
  const fileRef = useRef<HTMLInputElement>(null)

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [catRes, docRes] = await Promise.all([
        apiGet<{ categories: DocCategory[] }>(`/api/studio/categories/${founder}`),
        apiGet<{ documents: StudioDocument[] }>(`/api/studio/documents/${founder}`),
      ])
      setCategories(catRes.categories || [])
      setDocuments(docRes.documents || [])
    } catch {
    } finally {
      setLoading(false)
    }
  }, [founder])

  useEffect(() => { loadAll() }, [loadAll])

  const createCategory = async () => {
    if (!newCatName.trim()) return
    try {
      await apiPost('/api/studio/categories', { founder_slug: founder, name: newCatName.trim() })
      setNewCatName('')
      await loadAll()
    } catch (e: any) {
      alert(e.message || 'Failed to create category')
    }
  }

  const deleteCategory = async (id: string) => {
    if (!confirm('Delete this category? Documents will become uncategorized.')) return
    try {
      await apiDelete(`/api/studio/categories/${id}`)
      await loadAll()
    } catch {}
  }

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0]
    if (!file) { alert('Select a file'); return }
    setUploading(true)
    try {
      await apiUploadWithFields('/api/studio/documents/upload', file, {
        founder_slug: founder,
        category_id: selectedCat,
      })
      if (fileRef.current) fileRef.current.value = ''
      await loadAll()
    } catch (e: any) {
      alert(e.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const deleteDocument = async (id: string) => {
    if (!confirm('Delete this document?')) return
    try {
      await apiDelete(`/api/studio/documents/${id}`)
      setDocuments(prev => prev.filter(d => d.document_id !== id))
    } catch {}
  }

  const moveDocument = async (docId: string, catId: string | null) => {
    try {
      await apiPut(`/api/studio/documents/${docId}/category`, { category_id: catId })
      setDocuments(prev => prev.map(d => d.document_id === docId ? { ...d, category_id: catId } : d))
    } catch {}
  }

  const grouped = categories.map(c => ({
    ...c,
    docs: documents.filter(d => d.category_id === c.category_id),
  }))
  const uncategorized = documents.filter(d => !d.category_id)

  return (
    <div className="space-y-5">
      {/* Upload */}
      <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
        <h2 className="mb-4 text-[14px] font-semibold text-[var(--text-primary)]">
          <Upload size={14} className="mr-2 inline text-[var(--text-muted)]" />
          Upload Document
        </h2>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">File</label>
            <input ref={fileRef} type="file" accept=".txt,.md,.docx,.xlsx,.xls,.csv,.pdf,.json,.yaml,.yml" className="field w-full text-[12px]" />
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Category</label>
            <select
              value={selectedCat}
              onChange={e => setSelectedCat(e.target.value)}
              className="field w-full"
            >
              <option value="">Uncategorized</option>
              {categories.map(c => (
                <option key={c.category_id} value={c.category_id}>{c.name}</option>
              ))}
            </select>
          </div>
        </div>

        <button
          onClick={handleUpload}
          disabled={uploading}
          className="mt-3 flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-[13px] font-semibold text-black transition-all hover:bg-white/90 disabled:opacity-40"
        >
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
          {uploading ? 'Uploading...' : 'Upload'}
        </button>
      </div>

      {/* Category Management */}
      <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
        <h2 className="mb-4 text-[14px] font-semibold text-[var(--text-primary)]">
          <FolderPlus size={14} className="mr-2 inline text-[var(--text-muted)]" />
          Categories
        </h2>

        <div className="mb-3 flex gap-2">
          <input
            type="text"
            value={newCatName}
            onChange={e => setNewCatName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && createCategory()}
            placeholder="New category name..."
            className="field flex-1"
          />
          <button
            onClick={createCategory}
            disabled={!newCatName.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-[var(--surface-3)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-4)] disabled:opacity-40"
          >
            <Plus size={13} />
            Add
          </button>
        </div>

        {categories.length === 0 ? (
          <p className="text-[12px] text-[var(--text-muted)]">No categories yet. Create one above.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {categories.map(c => (
              <div key={c.category_id} className="flex items-center gap-1.5 rounded-lg bg-[var(--surface-3)] px-3 py-1.5">
                <FolderOpen size={12} className="text-[var(--text-muted)]" />
                <span className="text-[12px] font-medium text-[var(--text-secondary)]">{c.name}</span>
                <span className="text-[10px] text-[var(--text-muted)]">
                  ({documents.filter(d => d.category_id === c.category_id).length})
                </span>
                <button
                  onClick={() => deleteCategory(c.category_id)}
                  className="ml-1 text-[var(--text-muted)] hover:text-[var(--error, #ef4444)]"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Document List */}
      <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
        <h2 className="mb-4 text-[14px] font-semibold text-[var(--text-primary)]">
          <FileText size={14} className="mr-2 inline text-[var(--text-muted)]" />
          Document Library
        </h2>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={18} className="animate-spin text-[var(--text-muted)]" />
          </div>
        ) : documents.length === 0 ? (
          <p className="py-4 text-center text-[13px] text-[var(--text-muted)]">No documents uploaded yet</p>
        ) : (
          <div className="space-y-4">
            {grouped.filter(g => g.docs.length > 0).map(g => (
              <div key={g.category_id}>
                <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                  <FolderOpen size={12} />
                  {g.name} ({g.docs.length})
                </p>
                <div className="space-y-1.5">
                  {g.docs.map(d => (
                    <DocRow key={d.document_id} doc={d} categories={categories} onDelete={deleteDocument} onMove={moveDocument} />
                  ))}
                </div>
              </div>
            ))}

            {uncategorized.length > 0 && (
              <div>
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                  Uncategorized ({uncategorized.length})
                </p>
                <div className="space-y-1.5">
                  {uncategorized.map(d => (
                    <DocRow key={d.document_id} doc={d} categories={categories} onDelete={deleteDocument} onMove={moveDocument} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function DocRow({ doc, categories, onDelete, onMove }: {
  doc: StudioDocument
  categories: DocCategory[]
  onDelete: (id: string) => void
  onMove: (docId: string, catId: string | null) => void
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-[var(--border-2)] p-3">
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium text-[var(--text-primary)]">{doc.filename}</p>
        <div className="mt-1 flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
          <span>{doc.file_type}</span>
          <span>·</span>
          <span>{(doc.text_length / 1000).toFixed(1)}k chars</span>
          <span>·</span>
          <span>{new Date(doc.created_at).toLocaleDateString()}</span>
        </div>
      </div>
      <select
        value={doc.category_id || ''}
        onChange={e => onMove(doc.document_id, e.target.value || null)}
        className="rounded-lg bg-[var(--surface-3)] px-2 py-1 text-[11px] text-[var(--text-secondary)] outline-none"
      >
        <option value="">Uncategorized</option>
        {categories.map(c => (
          <option key={c.category_id} value={c.category_id}>{c.name}</option>
        ))}
      </select>
      <button
        onClick={() => onDelete(doc.document_id)}
        className="rounded-lg p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--error, #ef4444)]"
      >
        <Trash2 size={13} />
      </button>
    </div>
  )
}

// ── History Tab ──────────────────────────────────────────────────────────

function HistoryTab() {
  const founder = useFounderStore(s => s.active)
  const [blogs, setBlogs] = useState<BlogMeta[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedBlog, setSelectedBlog] = useState<string | null>(null)
  const [blogContent, setBlogContent] = useState('')

  const loadBlogs = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiGet<{ blogs: BlogMeta[] }>(`/api/blog/list/${founder}`)
      setBlogs(res.blogs || [])
    } catch (e) {
      console.error('Failed to load blogs:', e)
    } finally {
      setLoading(false)
    }
  }, [founder])

  useEffect(() => { loadBlogs() }, [loadBlogs])

  const viewBlog = async (blogId: string) => {
    if (selectedBlog === blogId) {
      setSelectedBlog(null)
      return
    }
    try {
      const res = await apiGet<{ content: string }>(`/api/blog/${blogId}`)
      setBlogContent(res.content || '')
      setSelectedBlog(blogId)
    } catch (e) {
      console.error('Failed to load blog:', e)
    }
  }

  const deleteBlog = async (blogId: string) => {
    if (!confirm('Delete this blog post?')) return
    try {
      await apiDelete(`/api/blog/${blogId}`)
      setBlogs(prev => prev.filter(b => b.blog_id !== blogId))
      if (selectedBlog === blogId) setSelectedBlog(null)
    } catch (e) {
      console.error('Failed to delete blog:', e)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 size={20} className="animate-spin text-[var(--text-muted)]" />
      </div>
    )
  }

  if (!blogs.length) {
    return (
      <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-8 text-center">
        <FileText size={32} className="mx-auto mb-3 text-[var(--text-muted)]" />
        <p className="text-[14px] text-[var(--text-secondary)]">No blogs generated yet</p>
        <p className="text-[12px] text-[var(--text-muted)]">Use the Blogs or Narrative tab to generate your first post</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {blogs.map(blog => (
        <div key={blog.blog_id} className="rounded-xl border border-[var(--border-1)] bg-[var(--surface-1)] overflow-hidden">
          <div
            className="flex cursor-pointer items-center gap-3 p-4 transition-colors hover:bg-[var(--surface-2)]"
            onClick={() => viewBlog(blog.blog_id)}
          >
            {selectedBlog === blog.blog_id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-[var(--text-primary)]">{blog.title}</p>
              <div className="mt-1 flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
                <span>{blog.topic}</span>
                <span>·</span>
                <span>{blog.word_count} words</span>
                <span>·</span>
                <span>{new Date(blog.created_at).toLocaleDateString()}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {statusBadge(blog.status)}
              <span className="rounded bg-[var(--surface-3)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
                {blog.format_type}
              </span>
              <button
                onClick={e => { e.stopPropagation(); deleteBlog(blog.blog_id) }}
                className="rounded-lg p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--error, #ef4444)]"
              >
                <Trash2 size={13} />
              </button>
            </div>
          </div>
          {selectedBlog === blog.blog_id && blogContent && (
            <div className="border-t border-[var(--border-2)] p-5">
              <pre className="whitespace-pre-wrap font-[var(--font-body)] text-[13px] leading-relaxed text-[var(--text-secondary)]">
                {blogContent}
              </pre>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Shared Components ────────────────────────────────────────────────────

function PipelineProgress({ status }: { status: TaskStatus }) {
  const stages = status.log.filter(l => l.status === 'completed' || l.status === 'started')

  return (
    <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-[13px] font-semibold text-[var(--text-primary)]">Pipeline Progress</h3>
        <span className="text-[11px] text-[var(--text-muted)]">
          {status.status === 'running' ? `${(status.progress * 100).toFixed(0)}%` : status.status}
        </span>
      </div>

      <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-[var(--surface-3)]">
        <div
          className="h-full rounded-full bg-white transition-all duration-500"
          style={{ width: `${status.progress * 100}%` }}
        />
      </div>

      <div className="space-y-1.5">
        {stages.map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-[12px]">
            {s.status === 'completed' ? (
              <Check size={12} className="text-[var(--success)]" />
            ) : (
              <Loader2 size={12} className="animate-spin text-[var(--text-muted)]" />
            )}
            <span className={s.status === 'completed' ? 'text-[var(--text-secondary)]' : 'text-[var(--text-primary)]'}>
              {s.stage.replace(/_/g, ' ')}
            </span>
          </div>
        ))}
      </div>

      {status.error && (
        <div className="mt-3 rounded-lg bg-[var(--error-dim, rgba(239,68,68,0.1))] px-3 py-2 text-[12px] text-[var(--error, #ef4444)]">
          {status.error}
        </div>
      )}
    </div>
  )
}

function BlogResult({ result, blogId }: { result: any; blogId: string | null }) {
  const [expanded, setExpanded] = useState(false)
  const [content, setContent] = useState('')

  const loadContent = async () => {
    if (!blogId) return
    if (expanded) { setExpanded(false); return }
    try {
      const res = await apiGet<{ content: string }>(`/api/blog/${blogId}`)
      setContent(res.content || '')
      setExpanded(true)
    } catch (e) {
      console.error('Failed to load blog:', e)
    }
  }

  return (
    <div className="rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-5">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-[15px] font-semibold text-[var(--text-primary)]">{result.title}</h3>
          <div className="mt-1 flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
            <span>{result.word_count} words</span>
            <span>·</span>
            <span>Voice: {result.voice_validation?.overall || 'N/A'}</span>
            <span>·</span>
            <span>{result.tone}</span>
          </div>
        </div>
        <button
          onClick={loadContent}
          className="flex items-center gap-2 rounded-lg bg-[var(--surface-3)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-primary)] transition-colors hover:bg-[var(--surface-4)]"
        >
          <FileText size={13} />
          {expanded ? 'Hide' : 'View Post'}
        </button>
      </div>

      {expanded && content && (
        <div className="mt-4 rounded-xl border border-[var(--border-2)] bg-[var(--surface-2)] p-5">
          <pre className="whitespace-pre-wrap font-[var(--font-body)] text-[13px] leading-relaxed text-[var(--text-secondary)]">
            {content}
          </pre>
        </div>
      )}
    </div>
  )
}
