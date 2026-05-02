import { useState, useRef, useCallback, useEffect } from 'react'
import { Wand2, Loader2, Zap, Sparkles, Flame, StopCircle } from 'lucide-react'
import clsx from 'clsx'
import { apiGet, apiPost } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import PostBrowser from '../components/customize/PostBrowser'
import CreativityControls, {
  type CreativityValues,
} from '../components/customize/CreativityControls'
import DiffPreview from '../components/customize/DiffPreview'
import PipelineBuilder from '../components/customize/PipelineBuilder'
import type { CustomizationResult, PipelineConfig, PipelineDefaultsResponse } from '../types/api'
import { PageHeader, Card, CardHeader, CardBody, CardTitle, Button } from '../components/ui'

type Tab = 'browse' | 'custom'
type PipelineMode = 'quick' | 'full' | 'v2'

interface PipelineStep {
  id: string
  label: string
  status: 'pending' | 'active' | 'completed'
}

const FULL_PIPELINE_STEPS: PipelineStep[] = [
  { id: 'generate_variants', label: 'Generate 5 Variants', status: 'pending' },
  { id: 'audience_vote', label: 'Audience Voting', status: 'pending' },
  { id: 'refine', label: 'Refine Top 2', status: 'pending' },
  { id: 'opening_massacre', label: 'Opening Massacre', status: 'pending' },
  { id: 'humanize', label: 'Humanize + Quality Gate', status: 'pending' },
]

const V2_PIPELINE_STEPS: PipelineStep[] = [
  { id: 'internalize_founder', label: 'Internalize Founder', status: 'pending' },
  { id: 'dissect_source', label: 'Dissect Source Post', status: 'pending' },
  { id: 'generate_adaptations', label: 'Generate 5 Adaptations', status: 'pending' },
  { id: 'audience_vote', label: 'Audience Voting', status: 'pending' },
  { id: 'refine', label: 'Refine Top Posts', status: 'pending' },
  { id: 'quality_filter', label: '11-Point Quality Filter', status: 'pending' },
  { id: 'track_coverage', label: 'Track Coverage', status: 'pending' },
]

const MODE_META = {
  quick: {
    icon: <Zap size={13} />,
    label: 'Quick',
    description: 'Per-section voice adaptation (fast, 3 LLM calls)',
  },
  full: {
    icon: <Sparkles size={13} />,
    label: 'Full',
    description: '5 variants → audience vote → refine → opening massacre → humanize',
  },
  v2: {
    icon: <Flame size={13} />,
    label: 'V2 Adapt',
    description: 'Deep internalization → dissect hook → 5 adapted versions → vote → quality filter',
  },
}

export default function CustomizePage() {
  const [tab, setTab] = useState<Tab>('browse')
  const [mode, setMode] = useState<PipelineMode>('quick')
  const [numVariants] = useState<number>(5)
  const [showThinking, setShowThinking] = useState<boolean>(true)
  const [skipVoting] = useState<boolean>(true)

  const [pipelineDefaults, setPipelineDefaults] = useState<PipelineDefaultsResponse | null>(null)
  const [pipelineConfig, setPipelineConfig] = useState<PipelineConfig>({})

  useEffect(() => {
    apiGet<PipelineDefaultsResponse>('/api/posts/customize/config/defaults')
      .then((d) => { setPipelineDefaults(d); setPipelineConfig(d.defaults) })
      .catch(() => {})
  }, [])

  const [selectedText, setSelectedText] = useState('')
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null)
  const [customText, setCustomText] = useState('')

  const [creativity, setCreativity] = useState<CreativityValues>({
    opening: 50, body: 50, closing: 50, tone: 50,
  })

  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CustomizationResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([])
  const [pipelineLog, setPipelineLog] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)

  const active = useFounderStore((s) => s.active)
  const activeText = tab === 'browse' ? selectedText : customText
  const canCustomize = activeText.trim().length > 0

  const handleSelectPost = (text: string, postId: string) => {
    setSelectedText(text); setSelectedPostId(postId); setResult(null); setError(null)
  }

  const handleCreativityChange = (key: keyof CreativityValues, value: number) => {
    setCreativity((prev) => ({ ...prev, [key]: value }))
  }

  const handleQuickCustomize = async () => {
    if (!canCustomize) return
    setLoading(true); setError(null); setResult(null)
    try {
      const res = await apiPost<CustomizationResult>('/api/posts/customize', {
        text: activeText, founder_slug: active,
        creativity_opening: creativity.opening / 100,
        creativity_body: creativity.body / 100,
        creativity_closing: creativity.closing / 100,
        creativity_tone: creativity.tone / 100,
        num_variants: 5, skip_voting: true,
      })
      setResult(res)
    } catch (e: any) {
      setError(e.message || 'Customization failed')
    } finally {
      setLoading(false)
    }
  }

  const handleFullCustomize = useCallback(async () => {
    if (!canCustomize) return
    setLoading(true); setError(null); setResult(null)
    setPipelineSteps(FULL_PIPELINE_STEPS.map((s) => ({ ...s, status: 'pending' })))
    setPipelineLog([])
    const abort = new AbortController()
    abortRef.current = abort

    try {
      const body = JSON.stringify({
        text: activeText, founder_slug: active,
        creativity_opening: creativity.opening / 100,
        creativity_body: creativity.body / 100,
        creativity_closing: creativity.closing / 100,
        creativity_tone: creativity.tone / 100,
        num_variants: pipelineConfig?.variants?.n ?? numVariants,
        skip_voting: pipelineConfig?.audience_vote?.enabled === false ? true : skipVoting,
        pipeline: pipelineConfig,
      })

      const resp = await fetch('/api/posts/customize/full', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: abort.signal,
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const reader = resp.body?.getReader()
      if (!reader) throw new Error('No response stream')
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const json = line.slice(6).trim()
          if (!json || json === '[DONE]') continue
          try {
            const event = JSON.parse(json)
            const { stage, status, data } = event
            if (stage === 'pipeline_plan' && status === 'started' && Array.isArray(data?.stages)) {
              const enabledStages = data.stages.filter((s: any) => s.enabled)
              setPipelineSteps(enabledStages.map((s: any) => ({ id: s.id, label: s.label, status: 'pending' as const })))
              setPipelineLog((prev) => [...prev, `Plan: ${data.expected_llm_calls} expected LLM calls`])
              continue
            }
            setPipelineSteps((prev) => prev.map((step) => {
              if (step.id !== stage) return step
              if (status === 'started' || status === 'generating' || status === 'voting' || status === 'progress') return { ...step, status: 'active' }
              if (status === 'completed') return { ...step, status: 'completed' }
              return step
            }))
            if (stage === 'generate_variants' && status === 'progress') setPipelineLog((prev) => [...prev, `Generating variant: ${data?.strategy || '?'}`])
            if (stage === 'audience_vote' && status === 'progress') setPipelineLog((prev) => [...prev, `Vote from: ${data?.agent_name || '?'}`])
            if (stage === 'opening_massacre' && status === 'generating') setPipelineLog((prev) => [...prev, `Generated ${data?.count || 0} opening lines`])
            if (stage === 'quality_gate' && status === 'completed') setPipelineLog((prev) => [...prev, `Quality: ${data?.score || 0}% (${data?.passed ? 'PASS' : 'FAIL'})`])
            if (stage === 'skip_voting' && status === 'started') setPipelineLog((prev) => [...prev, `Skipping voting. Humanizing ${data?.count || 0} variants…`])
            if (stage === 'done') {
              if (data?.error) { setError(data.error) } else {
                setResult({ original: data.original || activeText, customized: data.customized || '', sections: data.sections || {}, topic: data.topic || '', founder_context: data.founder_context || {}, viral_context: data.viral_context || {}, traceability: data.traceability, all_variants: data.all_variants, quality: data.quality })
                setPipelineSteps((prev) => prev.map((s) => ({ ...s, status: 'completed' })))
              }
            }
            if (stage === 'error') setError(data?.error || 'Pipeline failed')
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') setError(e.message || 'Full pipeline failed')
    } finally {
      setLoading(false); abortRef.current = null
    }
  }, [canCustomize, activeText, active, creativity, pipelineConfig, numVariants, skipVoting])

  const handleV2Adapt = useCallback(async () => {
    if (!canCustomize) return
    setLoading(true); setError(null); setResult(null)
    setPipelineSteps(V2_PIPELINE_STEPS.map((s) => ({ ...s, status: 'pending' })))
    setPipelineLog([])
    const abort = new AbortController()
    abortRef.current = abort

    try {
      const body = JSON.stringify({ source_post: activeText, founder_slug: active, platform: 'linkedin', creativity: creativity.tone / 100, num_variants: 5 })
      const resp = await fetch('/api/posts/adapt-v2/stream', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: abort.signal,
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const reader = resp.body?.getReader()
      if (!reader) throw new Error('No response stream')
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const json = line.slice(6).trim()
          if (!json || json === '[DONE]') continue
          try {
            const event = JSON.parse(json)
            const { stage, status, data } = event
            setPipelineSteps((prev) => prev.map((step) => {
              if (step.id !== stage) return step
              if (status === 'started' || status === 'progress') return { ...step, status: 'active' }
              if (status === 'completed') return { ...step, status: 'completed' }
              return step
            }))
            if (stage === 'internalize_founder' && status === 'completed') setPipelineLog((prev) => [...prev, `Internalized: ${data?.tensions_count || 0} tensions, ${data?.scenes_count || 0} scenes`])
            if (stage === 'dissect_source' && status === 'completed') setPipelineLog((prev) => [...prev, `Dissected: ${data?.hook_count || 0} hook sentences, arc: ${data?.narrative_arc || '?'}`])
            if (stage === 'generate_adaptations' && status === 'progress') setPipelineLog((prev) => [...prev, `Adapting variant ${(data?.index ?? 0) + 1}: ${data?.register || '?'}`])
            if (stage === 'audience_vote' && status === 'progress') setPipelineLog((prev) => [...prev, `Vote from: ${data?.agent_name || '?'}`])
            if (stage === 'quality_filter' && status === 'progress') setPipelineLog((prev) => [...prev, `Quality: ${data?.post_id || '?'} — ${data?.passed ? 'PASS' : 'FAIL'} (${data?.failures || 0} failures)`])
            if (stage === 'done') {
              if (data?.error) { setError(data.error) } else {
                setResult({ original: data.original || activeText, customized: data.customized || '', sections: data.sections || {}, topic: data.topic || '', founder_context: data.founder_context || {}, viral_context: data.viral_context || {}, traceability: data.traceability, all_variants: data.all_variants, quality: data.quality, founder_internalization: data.founder_internalization, source_dissection: data.source_dissection, events_used: data.events_used, v2_quality: data.v2_quality })
                setPipelineSteps((prev) => prev.map((s) => ({ ...s, status: 'completed' })))
              }
            }
            if (stage === 'error') setError(data?.error || 'V2 pipeline failed')
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') setError(e.message || 'V2 adaptation failed')
    } finally {
      setLoading(false); abortRef.current = null
    }
  }, [canCustomize, activeText, active, creativity])

  const handleCustomize = mode === 'v2' ? handleV2Adapt : mode === 'quick' ? handleQuickCustomize : handleFullCustomize

  const handleStop = () => {
    abortRef.current?.abort()
    setLoading(false)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Post Customizer"
        subtitle="Adapt existing posts with AI voice matching"
      />

      <div className="flex flex-col gap-6 lg:flex-row">
        {/* Left panel — post selection */}
        <div className="flex flex-col gap-4 lg:flex-1">
          {/* Tabs */}
          <div className="flex border-b border-[var(--border-1)]">
            {(['browse', 'custom'] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={clsx(
                  'border-b-2 px-4 py-2.5 text-[13px] font-medium transition-colors',
                  tab === t
                    ? 'border-white text-[var(--text-primary)]'
                    : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-secondary)]',
                )}
              >
                {t === 'browse' ? 'Browse Database' : 'Paste Custom'}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <Card className="flex-1">
            <CardBody className="h-full min-h-[320px]">
              {tab === 'browse' ? (
                <PostBrowser onSelectPost={handleSelectPost} selectedPostId={selectedPostId} />
              ) : (
                <div className="flex h-full flex-col">
                  <textarea
                    value={customText}
                    onChange={(e) => { setCustomText(e.target.value); setResult(null); setError(null) }}
                    placeholder="Paste a post here to customize it…"
                    className="field min-h-[260px] flex-1 resize-none"
                  />
                  <div className="mt-2 text-right text-[11px] text-[var(--text-muted)]">
                    {customText.length} characters
                  </div>
                </div>
              )}
            </CardBody>
          </Card>
        </div>

        {/* Right panel — controls */}
        <div className="flex flex-col gap-4 lg:w-[340px]">
          {/* Active founder */}
          <Card>
            <CardBody>
              <p className="text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Active Founder</p>
              <p className="mt-1 font-[var(--font-mono)] text-[13px] text-[var(--text-primary)]">{active}</p>
            </CardBody>
          </Card>

          {/* Pipeline mode */}
          <Card>
            <CardHeader>
              <CardTitle>Pipeline Mode</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <div className="flex gap-1.5">
                {(Object.keys(MODE_META) as PipelineMode[]).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={clsx(
                      'flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-[12px] font-medium transition-colors',
                      mode === m
                        ? 'bg-white text-black'
                        : 'bg-[var(--surface-3)] text-[var(--text-muted)] hover:text-[var(--text-secondary)]',
                    )}
                  >
                    {MODE_META[m].icon}
                    {MODE_META[m].label}
                  </button>
                ))}
              </div>
              <p className="text-[11.5px] leading-relaxed text-[var(--text-muted)]">
                {MODE_META[mode].description}
              </p>
            </CardBody>
          </Card>

          {/* Creativity controls */}
          <Card>
            <CardBody>
              <CreativityControls values={creativity} onChange={handleCreativityChange} />
            </CardBody>
          </Card>

          {/* Full pipeline options */}
          {mode === 'full' && (
            <>
              <PipelineBuilder config={pipelineConfig} onChange={setPipelineConfig} defaults={pipelineDefaults} />
              <Card>
                <CardBody>
                  <label className="flex cursor-pointer items-center gap-2 text-[13px] text-[var(--text-secondary)]">
                    <input
                      type="checkbox"
                      checked={showThinking}
                      onChange={(e) => setShowThinking(e.target.checked)}
                      className="rounded border-[var(--border-3)] bg-[var(--surface-3)]"
                    />
                    Show pipeline progress log
                  </label>
                </CardBody>
              </Card>
            </>
          )}

          {/* Action button */}
          {loading ? (
            <div className="flex gap-2">
              <Button variant="secondary" className="flex-1" disabled icon={<Loader2 size={14} className="animate-spin" />}>
                {mode === 'v2' ? 'Running V2…' : mode === 'quick' ? 'Customizing…' : 'Running pipeline…'}
              </Button>
              <Button variant="ghost" size="sm" onClick={handleStop} icon={<StopCircle size={14} />}>
                Stop
              </Button>
            </div>
          ) : (
            <Button
              onClick={handleCustomize}
              disabled={!canCustomize}
              className="w-full"
              icon={mode === 'v2' ? <Flame size={14} /> : mode === 'quick' ? <Wand2 size={14} /> : <Sparkles size={14} />}
            >
              {mode === 'v2' ? 'Run V2 Adaptation' : mode === 'quick' ? 'Quick Customize' : 'Run Full Pipeline'}
            </Button>
          )}

          {/* Pipeline progress */}
          {(mode === 'full' || mode === 'v2') && pipelineSteps.length > 0 && loading && (
            <Card className="animate-slide-up">
              <CardHeader>
                <CardTitle>{mode === 'v2' ? 'V2 Adaptation Progress' : 'Pipeline Progress'}</CardTitle>
              </CardHeader>
              <CardBody className="space-y-2">
                {pipelineSteps.map((step) => (
                  <div key={step.id} className="flex items-center gap-2.5">
                    <div className={clsx(
                      'h-2 w-2 rounded-full flex-shrink-0',
                      step.status === 'completed' && 'bg-[var(--success)]',
                      step.status === 'active' && 'bg-white animate-pulse',
                      step.status === 'pending' && 'bg-[var(--surface-4)]',
                    )} />
                    <span className={clsx(
                      'text-[12px]',
                      step.status === 'completed' && 'text-[var(--success)]',
                      step.status === 'active' && 'text-[var(--text-primary)]',
                      step.status === 'pending' && 'text-[var(--text-muted)]',
                    )}>
                      {step.label}
                    </span>
                  </div>
                ))}
                {pipelineLog.length > 0 && (
                  <div className="mt-2 max-h-28 overflow-auto border-t border-[var(--border-2)] pt-2 space-y-1">
                    {pipelineLog.slice(-8).map((msg, i) => (
                      <p key={i} className="text-[11px] text-[var(--text-muted)]">{msg}</p>
                    ))}
                  </div>
                )}
              </CardBody>
            </Card>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-xl border border-[var(--error)]/30 bg-[var(--error)]/10 px-4 py-3 text-[13px] text-[var(--error)]">
              {error}
            </div>
          )}

          {/* Result */}
          {result && (
            <Card className="animate-slide-up">
              <CardBody>
                <DiffPreview result={result} />
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
