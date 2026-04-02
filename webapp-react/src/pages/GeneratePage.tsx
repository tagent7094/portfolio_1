import { useRef, useState } from 'react'
import { Sparkles, Loader2, StopCircle } from 'lucide-react'
import { streamSSE } from '../api/client'
import { usePipelineStore } from '../store/usePipelineStore'
import { useFounderStore } from '../store/useFounderStore'
import PipelineStepper from '../components/generate/PipelineStepper'
import PostCard from '../components/generate/PostCard'
import VotingMatrix from '../components/generate/VotingMatrix'
import FinalResult from '../components/generate/FinalResult'

const PLATFORMS = ['linkedin', 'twitter', 'blog', 'email'] as const

export default function GeneratePage() {
  const [topic, setTopic] = useState('')
  const [platform, setPlatform] = useState<string>('linkedin')
  const [creativity, setCreativity] = useState(50)
  const [numVariants, setNumVariants] = useState(5)
  const [showThinking, setShowThinking] = useState(true)
  const abortRef = useRef<AbortController | null>(null)

  const active = useFounderStore((s) => s.active)
  const store = usePipelineStore()

  const handleGenerate = async () => {
    if (!topic.trim()) return

    console.log('[Generate] Starting pipeline:', { topic, platform, creativity: creativity / 100, founder_slug: active, num_variants: numVariants })

    store.reset()
    store.setRunning(true)

    const controller = new AbortController()
    abortRef.current = controller

    try {
      await streamSSE(
        '/api/generate/topic/stream',
        { topic, platform, creativity: creativity / 100, founder_slug: active, num_variants: numVariants },
        (event) => {
          console.log('[SSE Event]', event.stage, event.status, event.data ? Object.keys(event.data) : '')
          store.handleEvent(event)
        },
        controller.signal,
      )
      console.log('[Generate] Pipeline complete')
    } catch (e: any) {
      console.error('[Generate] Error:', e)
      if (e.name !== 'AbortError') {
        usePipelineStore.setState({ error: e.message, running: false })
      }
    }
  }

  const handleStop = () => {
    abortRef.current?.abort()
    store.setRunning(false)
  }

  const hasSteps = Object.keys(store.stepStates).length > 0

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Generate Content</h2>

      {/* Topic Form */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="sm:col-span-3">
            <label className="mb-1 block text-sm font-medium text-gray-300">
              Topic
            </label>
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="What should we write about?"
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-500 focus:border-indigo-500 focus:outline-none"
              onKeyDown={(e) => e.key === 'Enter' && !store.running && handleGenerate()}
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-300">
              Platform
            </label>
            <select
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-indigo-500 focus:outline-none"
            >
              {PLATFORMS.map((p) => (
                <option key={p} value={p}>
                  {p.charAt(0).toUpperCase() + p.slice(1)}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-300">
              Creativity: {creativity}%
            </label>
            <input
              type="range"
              min={0}
              max={100}
              value={creativity}
              onChange={(e) => setCreativity(Number(e.target.value))}
              className="w-full accent-indigo-500"
            />
          </div>

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
                  {num} posts
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-end gap-3 sm:col-span-2">
            <label className="flex items-center gap-2 text-sm text-gray-300 mb-2 cursor-pointer">
              <input
                type="checkbox"
                checked={showThinking}
                onChange={(e) => setShowThinking(e.target.checked)}
                className="rounded border-gray-700 bg-gray-800 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-gray-900"
              />
              Show Thinking
            </label>

            <div className="flex-1"></div>

            {store.running ? (
              <button
                onClick={handleStop}
                className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500"
              >
                <StopCircle size={16} />
                Stop
              </button>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={async () => {
                    if (!topic.trim()) return
                    store.reset()
                    store.setRunning(true)
                    try {
                      const { apiPost } = await import('../api/client')
                      const res = await apiPost<{ post: string }>('/api/generate/quick-fix', { topic, platform, creativity: creativity / 100, founder_slug: active })
                      store.handleEvent({
                        stage: 'done', status: 'pipeline_done', data: { quality: { score: 0, passed: true }, influence: { overall: 0, belief_alignment: { score: 0 }, story_influence: { score: 0 }, style_adherence: { score: 0 } }, post: res.post },
                        progress: 0,
                        agent_id: ''
                      })
                    } catch (e: any) {
                      usePipelineStore.setState({ error: e.message, running: false })
                    }
                  }}
                  disabled={!topic.trim()}
                  className="flex items-center gap-2 rounded-lg bg-gray-700 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-600 disabled:opacity-50"
                  title="Generate a structural variant instantly, skipping voting protocols"
                >
                  <Sparkles size={16} className="text-yellow-400" />
                  Quick Fix
                </button>
                <button
                  onClick={handleGenerate}
                  disabled={!topic.trim()}
                  className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
                >
                  <Sparkles size={16} />
                  Full Generate
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Error */}
      {store.error && (
        <div className="rounded-lg border border-red-800 bg-red-950/50 px-4 py-3 text-sm text-red-300">
          {store.error}
        </div>
      )}

      {/* Pipeline Stepper */}
      {showThinking && hasSteps && (
        <PipelineStepper stepStates={store.stepStates} />
      )}

      {/* Running indicator */}
      {store.running && (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <Loader2 size={16} className="animate-spin" />
          Pipeline running...
        </div>
      )}

      {/* Stage 1: Posts */}
      {showThinking && store.posts.length > 0 && (
        <div>
          <h3 className="mb-3 text-lg font-semibold text-gray-200">
            Generated Posts
          </h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {store.posts.map((post) => (
              <PostCard
                key={post.id}
                post={post}
                streamingText={store.streamingTokens[post.engine_id]}
              />
            ))}
          </div>
        </div>
      )}

      {/* Stage 2: Voting Matrix */}
      {showThinking && Object.keys(store.votes).length > 0 && (
        <VotingMatrix
          posts={store.posts}
          votes={store.votes}
          agentNames={store.agentNames}
        />
      )}

      {/* Stage 3: Refinement */}
      {showThinking && store.refinedPosts.length > 0 && (
        <div>
          <h3 className="mb-3 text-lg font-semibold text-gray-200">
            Refined Posts
          </h3>
          <div className="space-y-3">
            {store.refinedPosts.map((rp: any, i: number) => (
              <div
                key={i}
                className="grid gap-4 rounded-xl border border-gray-800 bg-gray-900 p-4 sm:grid-cols-2"
              >
                <div>
                  <span className="mb-1 block text-xs font-medium text-gray-500">
                    Before
                  </span>
                  <p className="text-sm text-gray-400">{rp.original_text || rp.original || rp.before || ''}</p>
                </div>
                <div>
                  <span className="mb-1 block text-xs font-medium text-indigo-400">
                    After
                  </span>
                  <p className="text-sm text-gray-200">{rp.refined_text || rp.refined || rp.after || ''}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stage 4: Opening Massacre */}
      {showThinking && store.openingLines.length > 0 && (
        <div>
          <h3 className="mb-3 text-lg font-semibold text-gray-200">
            Opening Lines
          </h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {store.openingLines.map((line) => (
              <div
                key={line.id}
                className={`rounded-lg border p-3 text-sm ${store.winningOpening?.text === line.text
                  ? 'border-green-600 bg-green-950/30 text-green-200'
                  : 'border-gray-800 bg-gray-900 text-gray-300'
                  }`}
              >
                <p>{line.text}</p>
                {line.strategy && (
                  <span className="mt-1 block text-xs text-gray-500">
                    {line.strategy}
                  </span>
                )}
              </div>
            ))}
          </div>
          {store.winningOpening && (
            <div className="mt-3 rounded-lg border border-green-700 bg-green-950/40 p-3">
              <span className="text-xs font-medium text-green-400">
                Winner
              </span>
              <p className="text-sm text-green-200">
                {store.winningOpening.text}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Stage 5: Final Result */}
      {store.result && <FinalResult result={store.result} />}
    </div>
  )
}
