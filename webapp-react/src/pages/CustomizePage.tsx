import { useState, useRef, useCallback } from 'react'
import { Wand2, Loader2, Zap, Sparkles } from 'lucide-react'
import clsx from 'clsx'
import { apiPost } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import PostBrowser from '../components/customize/PostBrowser'
import CreativityControls, {
  type CreativityValues,
} from '../components/customize/CreativityControls'
import DiffPreview from '../components/customize/DiffPreview'
import type { CustomizationResult } from '../types/api'

type Tab = 'browse' | 'custom'
type PipelineMode = 'quick' | 'full'

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

export default function CustomizePage() {
  const [tab, setTab] = useState<Tab>('browse')
  const [mode, setMode] = useState<PipelineMode>('quick')
  const [numVariants, setNumVariants] = useState<number>(5)
  const [showThinking, setShowThinking] = useState<boolean>(true)
  const [skipVoting, setSkipVoting] = useState<boolean>(true)

  // Post selection state
  const [selectedText, setSelectedText] = useState('')
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null)
  const [customText, setCustomText] = useState('')

  // Creativity controls
  const [creativity, setCreativity] = useState<CreativityValues>({
    opening: 50,
    body: 50,
    closing: 50,
    tone: 50,
  })

  // API state
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CustomizationResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Full pipeline state
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([])
  const [pipelineLog, setPipelineLog] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)

  const active = useFounderStore((s) => s.active)

  const activeText = tab === 'browse' ? selectedText : customText
  const canCustomize = activeText.trim().length > 0

  const handleSelectPost = (text: string, postId: string) => {
    setSelectedText(text)
    setSelectedPostId(postId)
    setResult(null)
    setError(null)
  }

  const handleCreativityChange = (
    key: keyof CreativityValues,
    value: number,
  ) => {
    setCreativity((prev) => ({ ...prev, [key]: value }))
  }

  // Quick customization (existing behavior)
  const handleQuickCustomize = async () => {
    if (!canCustomize) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await apiPost<CustomizationResult>('/api/posts/customize', {
        text: activeText,
        founder_slug: active,
        creativity_opening: creativity.opening / 100,
        creativity_body: creativity.body / 100,
        creativity_closing: creativity.closing / 100,
        creativity_tone: creativity.tone / 100,
        num_variants: 5, // Requesting 5 by default for quick mode too as per user's "5 in quick section"
        skip_voting: true,
      })
      setResult(res)
    } catch (e: any) {
      setError(e.message || 'Customization failed')
    } finally {
      setLoading(false)
    }
  }

  // Full pipeline customization (SSE streaming)
  const handleFullCustomize = useCallback(async () => {
    if (!canCustomize) return
    setLoading(true)
    setError(null)
    setResult(null)
    setPipelineSteps(FULL_PIPELINE_STEPS.map((s) => ({ ...s, status: 'pending' })))
    setPipelineLog([])

    const abort = new AbortController()
    abortRef.current = abort

    try {
      const body = JSON.stringify({
        text: activeText,
        founder_slug: active,
        creativity_opening: creativity.opening / 100,
        creativity_body: creativity.body / 100,
        creativity_closing: creativity.closing / 100,
        creativity_tone: creativity.tone / 100,
        num_variants: numVariants,
        skip_voting: skipVoting,
      })

      const resp = await fetch('/api/posts/customize/full', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: abort.signal,
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

            // Update pipeline steps
            setPipelineSteps((prev) =>
              prev.map((step) => {
                if (step.id === stage) {
                  if (status === 'started' || status === 'generating' || status === 'voting' || status === 'progress') {
                    return { ...step, status: 'active' }
                  }
                  if (status === 'completed') {
                    return { ...step, status: 'completed' }
                  }
                }
                return step
              }),
            )

            // Build log messages
            if (stage === 'generate_variants' && status === 'progress') {
              setPipelineLog((prev) => [...prev, `Generating variant: ${data?.strategy || '?'}`])
            }
            if (stage === 'audience_vote' && status === 'progress') {
              setPipelineLog((prev) => [...prev, `Vote from: ${data?.agent_name || '?'}`])
            }
            if (stage === 'opening_massacre' && status === 'generating') {
              setPipelineLog((prev) => [...prev, `Generated ${data?.count || 0} opening lines`])
            }
            if (stage === 'quality_gate' && status === 'completed') {
              setPipelineLog((prev) => [...prev, `Quality: ${data?.score || 0}% (${data?.passed ? 'PASS' : 'FAIL'})`])
            }
            if (stage === 'skip_voting' && status === 'started') {
              setPipelineLog((prev) => [...prev, `Skipping voting. Humanizing ${data?.count || 0} variants...`])
            }

            // Final result
            if (stage === 'done') {
              if (data?.error) {
                setError(data.error)
              } else {
                setResult({
                  original: data.original || activeText,
                  customized: data.customized || '',
                  sections: data.sections || {},
                  topic: data.topic || '',
                  founder_context: data.founder_context || {},
                  viral_context: data.viral_context || {},
                  traceability: data.traceability,
                  all_variants: data.all_variants,
                  quality: data.quality,
                })
                setPipelineSteps((prev) => prev.map((s) => ({ ...s, status: 'completed' })))
              }
            }

            if (stage === 'error') {
              setError(data?.error || 'Pipeline failed')
            }
          } catch {
            // ignore parse errors
          }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setError(e.message || 'Full pipeline failed')
      }
    } finally {
      setLoading(false)
      abortRef.current = null
    }
  }, [canCustomize, activeText, active, creativity])

  const handleCustomize = mode === 'quick' ? handleQuickCustomize : handleFullCustomize

  return (
    <div className="flex h-full gap-6">
      {/* Left panel (60%) */}
      <div className="flex w-[60%] flex-col">
        <h2 className="mb-4 text-2xl font-bold">Post Customizer</h2>

        {/* Tab bar */}
        <div className="mb-4 flex gap-1 border-b border-gray-800">
          <button
            onClick={() => setTab('browse')}
            className={clsx(
              'border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              tab === 'browse'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-gray-400 hover:text-gray-200',
            )}
          >
            Browse Database
          </button>
          <button
            onClick={() => setTab('custom')}
            className={clsx(
              'border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              tab === 'custom'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-gray-400 hover:text-gray-200',
            )}
          >
            Paste Custom
          </button>
        </div>

        {/* Tab content */}
        <div className="min-h-0 flex-1 rounded-xl border border-gray-800 bg-gray-900 p-4">
          {tab === 'browse' ? (
            <PostBrowser
              onSelectPost={handleSelectPost}
              selectedPostId={selectedPostId}
            />
          ) : (
            <div className="flex h-full flex-col">
              <textarea
                value={customText}
                onChange={(e) => {
                  setCustomText(e.target.value)
                  setResult(null)
                  setError(null)
                }}
                placeholder="Paste a post here to customize it..."
                className="flex-1 resize-none rounded-lg border border-gray-700 bg-gray-800 p-3 text-sm text-gray-100 placeholder:text-gray-500 focus:border-indigo-500 focus:outline-none"
              />
              <div className="mt-2 text-right text-xs text-gray-500">
                {customText.length} characters
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right panel (40%) */}
      <div className="flex w-[40%] flex-col space-y-5 overflow-auto">
        {/* Founder info */}
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <div className="mb-1 text-xs font-medium text-gray-500">
            Active Founder
          </div>
          <div className="text-sm font-semibold text-gray-200">{active}</div>
        </div>

        {/* Pipeline mode toggle */}
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <div className="mb-2 text-xs font-medium text-gray-500">Pipeline Mode</div>
          <div className="flex gap-2">
            <button
              onClick={() => setMode('quick')}
              className={clsx(
                'flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                mode === 'quick'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-200',
              )}
            >
              <Zap size={14} />
              Quick
            </button>
            <button
              onClick={() => setMode('full')}
              className={clsx(
                'flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                mode === 'full'
                  ? 'bg-amber-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:text-gray-200',
              )}
            >
              <Sparkles size={14} />
              Full Pipeline
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-500">
            {mode === 'quick'
              ? 'Per-section voice adaptation (fast, 3 LLM calls)'
              : '5 variants → audience vote → refine → opening massacre → humanize'}
          </p>
        </div>

        {/* Creativity sliders */}
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <CreativityControls
            values={creativity}
            onChange={handleCreativityChange}
          />
        </div>

        {/* Pipeline options */}
        {mode === 'full' && (
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-300">
                  Variants
                </label>
                <select
                  value={numVariants}
                  onChange={(e) => setNumVariants(Number(e.target.value))}
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none"
                >
                  {[1, 3, 5, 10].map((num) => (
                    <option key={num} value={num}>
                      {num} variants
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col justify-end gap-2 pb-1">
                <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={showThinking}
                    onChange={(e) => setShowThinking(e.target.checked)}
                    className="rounded border-gray-700 bg-gray-800 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-gray-900"
                  />
                  Show Thinking
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={skipVoting}
                    onChange={(e) => setSkipVoting(e.target.checked)}
                    className="rounded border-gray-700 bg-gray-800 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-gray-900"
                  />
                  Skip Voting (Wave 12)
                </label>
              </div>
            </div>
          </div>
        )}

        {/* Customize button */}
        <button
          onClick={handleCustomize}
          disabled={!canCustomize || loading}
          className={clsx(
            'flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-white transition-colors disabled:opacity-50',
            mode === 'quick'
              ? 'bg-indigo-600 hover:bg-indigo-500'
              : 'bg-amber-600 hover:bg-amber-500',
          )}
        >
          {loading ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              {mode === 'quick' ? 'Customizing...' : 'Running Pipeline...'}
            </>
          ) : (
            <>
              {mode === 'quick' ? <Wand2 size={16} /> : <Sparkles size={16} />}
              {mode === 'quick' ? 'Quick Customize' : 'Run Full Pipeline'}
            </>
          )}
        </button>

        {/* Full pipeline progress */}
        {mode === 'full' && showThinking && pipelineSteps.length > 0 && loading && (
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <h4 className="mb-3 text-xs font-semibold text-amber-400">Pipeline Progress</h4>
            <div className="space-y-2">
              {pipelineSteps.map((step) => (
                <div key={step.id} className="flex items-center gap-2">
                  <div
                    className={clsx(
                      'h-2 w-2 rounded-full',
                      step.status === 'completed' && 'bg-green-500',
                      step.status === 'active' && 'bg-amber-500 animate-pulse',
                      step.status === 'pending' && 'bg-gray-700',
                    )}
                  />
                  <span
                    className={clsx(
                      'text-xs',
                      step.status === 'completed' && 'text-green-400',
                      step.status === 'active' && 'text-amber-300',
                      step.status === 'pending' && 'text-gray-600',
                    )}
                  >
                    {step.label}
                  </span>
                </div>
              ))}
            </div>
            {pipelineLog.length > 0 && (
              <div className="mt-3 max-h-32 overflow-auto border-t border-gray-800 pt-2">
                {pipelineLog.slice(-8).map((msg, i) => (
                  <p key={i} className="text-xs text-gray-500">{msg}</p>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-800 bg-red-950/50 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
            <DiffPreview result={result} />
          </div>
        )}
      </div>
    </div >
  )
}
