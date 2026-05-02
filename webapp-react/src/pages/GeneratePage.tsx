import { useRef, useState } from 'react'
import { Sparkles, StopCircle, Zap } from 'lucide-react'
import { streamSSE } from '../api/client'
import { usePipelineStore } from '../store/usePipelineStore'
import { useFounderStore } from '../store/useFounderStore'
import PipelineStepper from '../components/generate/PipelineStepper'
import PostCard from '../components/generate/PostCard'
import VotingMatrix from '../components/generate/VotingMatrix'
import FinalResult from '../components/generate/FinalResult'
import { PageHeader, Card, CardHeader, CardBody, CardTitle, Button, Badge } from '../components/ui'

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
    store.reset()
    store.setRunning(true)
    const controller = new AbortController()
    abortRef.current = controller
    try {
      await streamSSE(
        '/api/generate/topic/stream',
        { topic, platform, creativity: creativity / 100, founder_slug: active, num_variants: numVariants },
        (event) => store.handleEvent(event),
        controller.signal,
      )
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        usePipelineStore.setState({ error: e.message, running: false })
      }
    }
  }

  const handleQuickFix = async () => {
    if (!topic.trim()) return
    store.reset()
    store.setRunning(true)
    try {
      const { apiPost } = await import('../api/client')
      const res = await apiPost<{ post: string }>('/api/generate/quick-fix', {
        topic, platform, creativity: creativity / 100, founder_slug: active,
      })
      store.handleEvent({
        stage: 'done', status: 'pipeline_done',
        data: { quality: { score: 0, passed: true }, influence: { overall: 0, belief_alignment: { score: 0 }, story_influence: { score: 0 }, style_adherence: { score: 0 } }, post: res.post },
        progress: 0, agent_id: '',
      })
    } catch (e: any) {
      usePipelineStore.setState({ error: e.message, running: false })
    }
  }

  const handleStop = () => {
    abortRef.current?.abort()
    store.setRunning(false)
  }

  const hasSteps = Object.keys(store.stepStates).length > 0

  return (
    <div className="space-y-6">
      <PageHeader
        title="Generate Content"
        subtitle="AI-powered post generation with multi-agent pipeline"
      />

      {/* Topic Form */}
      <Card className="animate-slide-up">
        <CardBody className="space-y-4">
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
              Topic
            </label>
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="What should we write about?"
              className="field"
              onKeyDown={(e) => e.key === 'Enter' && !store.running && handleGenerate()}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Platform
              </label>
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                className="field"
              >
                {PLATFORMS.map((p) => (
                  <option key={p} value={p}>
                    {p.charAt(0).toUpperCase() + p.slice(1)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Variants
              </label>
              <select
                value={numVariants}
                onChange={(e) => setNumVariants(Number(e.target.value))}
                className="field"
              >
                {[1, 3, 5, 10].map((n) => (
                  <option key={n} value={n}>{n} posts</option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1.5 flex items-center justify-between text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                <span>Creativity</span>
                <span className="normal-case font-normal text-[var(--text-secondary)]">{creativity}%</span>
              </label>
              <input
                type="range"
                min={0}
                max={100}
                value={creativity}
                onChange={(e) => setCreativity(Number(e.target.value))}
                className="mt-2 w-full accent-white"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <label className="flex cursor-pointer items-center gap-2 text-[13px] text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={showThinking}
                onChange={(e) => setShowThinking(e.target.checked)}
                className="rounded border-[var(--border-3)] bg-[var(--surface-3)] text-white/80 focus:ring-white/30 focus:ring-offset-[var(--surface-1)]"
              />
              Show pipeline progress
            </label>

            <div className="flex items-center gap-2">
              {store.running ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleStop}
                  icon={<StopCircle size={14} />}
                >
                  Stop
                </Button>
              ) : (
                <>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleQuickFix}
                    disabled={!topic.trim()}
                    icon={<Zap size={14} />}
                    title="Generate a structural variant instantly, skipping voting"
                  >
                    Quick Fix
                  </Button>
                  <Button
                    onClick={handleGenerate}
                    disabled={!topic.trim()}
                    icon={<Sparkles size={14} />}
                    size="sm"
                  >
                    Full Generate
                  </Button>
                </>
              )}
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Error */}
      {store.error && (
        <div className="rounded-xl border border-[var(--error)]/30 bg-[var(--error)]/10 px-4 py-3 text-[13px] text-[var(--error)]">
          {store.error}
        </div>
      )}

      {/* Running indicator */}
      {store.running && (
        <div className="flex items-center gap-2.5 text-[13px] text-[var(--text-muted)]">
          <div className="h-2 w-2 animate-pulse rounded-full bg-[var(--warning)]" />
          Pipeline running…
        </div>
      )}

      {/* Pipeline Stepper */}
      {showThinking && hasSteps && (
        <PipelineStepper stepStates={store.stepStates} />
      )}

      {/* Stage 1: Generated Posts */}
      {showThinking && store.posts.length > 0 && (
        <Card className="animate-slide-up">
          <CardHeader>
            <CardTitle>Generated Posts</CardTitle>
            <Badge variant="default">{store.posts.length}</Badge>
          </CardHeader>
          <CardBody>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {store.posts.map((post) => (
                <PostCard
                  key={post.id}
                  post={post}
                  streamingText={store.streamingTokens[post.engine_id]}
                />
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Stage 2: Voting Matrix */}
      {showThinking && Object.keys(store.votes).length > 0 && (
        <VotingMatrix
          posts={store.posts}
          votes={store.votes}
          agentNames={store.agentNames}
        />
      )}

      {/* Stage 3: Refined Posts */}
      {showThinking && store.refinedPosts.length > 0 && (
        <Card className="animate-slide-up">
          <CardHeader>
            <CardTitle>Refined Posts</CardTitle>
            <Badge variant="success">{store.refinedPosts.length}</Badge>
          </CardHeader>
          <CardBody className="space-y-3">
            {store.refinedPosts.map((rp: any, i: number) => (
              <div
                key={i}
                className="grid gap-4 rounded-xl border border-[var(--border-2)] bg-[var(--surface-3)] p-4 sm:grid-cols-2"
              >
                <div>
                  <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Before</span>
                  <p className="text-[13px] leading-relaxed text-[var(--text-muted)]">{rp.original_text || rp.original || rp.before || ''}</p>
                </div>
                <div>
                  <span className="mb-1.5 block text-[10px] font-semibold uppercase tracking-widest text-[var(--success)]">After</span>
                  <p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">{rp.refined_text || rp.refined || rp.after || ''}</p>
                </div>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      {/* Stage 4: Opening Lines */}
      {showThinking && store.openingLines.length > 0 && (
        <Card className="animate-slide-up">
          <CardHeader>
            <CardTitle>Opening Lines</CardTitle>
            {store.winningOpening && <Badge variant="success">Winner selected</Badge>}
          </CardHeader>
          <CardBody className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
              {store.openingLines.map((line) => {
                const isWinner = store.winningOpening?.text === line.text
                return (
                  <div
                    key={line.id}
                    className={`rounded-xl border p-3 text-[13px] transition-colors ${
                      isWinner
                        ? 'border-[var(--success)]/40 bg-[var(--success-dim)]'
                        : 'border-[var(--border-2)] bg-[var(--surface-3)]'
                    }`}
                  >
                    <p className={isWinner ? 'text-[var(--success)]' : 'text-[var(--text-secondary)]'}>{line.text}</p>
                    {line.strategy && (
                      <span className="mt-1 block text-[11px] text-[var(--text-muted)]">{line.strategy}</span>
                    )}
                  </div>
                )
              })}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Stage 5: Final Result */}
      {store.result && <FinalResult result={store.result} />}
    </div>
  )
}
