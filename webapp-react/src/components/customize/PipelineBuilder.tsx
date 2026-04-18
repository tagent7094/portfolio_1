import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, RotateCcw, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import type { PipelineConfig, PipelineDefaultsResponse, StageConfig } from '../../types/api'

const THINKING_BUDGET_OPTIONS = [
  { label: 'Off', value: 0 },
  { label: 'Low (4K)', value: 4096 },
  { label: 'Medium (16K)', value: 16384 },
  { label: 'High (32K)', value: 32768 },
]

const MAX_LLM_CALLS = 250 // must match MAX_LLM_CALLS_PER_RUN in the backend

function estimateCalls(
  cfg: PipelineConfig,
  nVoteAgents: number,
  nOpeningAgents: number,
): number {
  const v = cfg.variants ?? { enabled: true }
  const av = cfg.audience_vote ?? { enabled: true }
  const rf = cfg.refine ?? { enabled: true }
  const om = cfg.opening_massacre ?? { enabled: true }
  const hu = cfg.humanize ?? { enabled: true }

  const nVariants = v.n ?? 5
  const nOpenings = om.n ?? 10
  const topK = Math.min(rf.top_k ?? 2, nVariants)

  let calls = v.enabled ? nVariants : 0
  if (av.enabled) calls += nVoteAgents * nVariants
  if (rf.enabled) calls += topK
  if (om.enabled) {
    calls += 1
    if (av.enabled) calls += nOpeningAgents * nOpenings
  }
  if (hu.enabled) calls += av.enabled ? 1 : nVariants
  return calls
}

interface StageCardProps {
  title: string
  description: string
  stageKey: keyof PipelineConfig
  config: StageConfig
  onChange: (partial: Partial<StageConfig>) => void
  children?: React.ReactNode
  supportsThinking: boolean
}

function StageCard({ title, description, config, onChange, children, supportsThinking }: StageCardProps) {
  const [open, setOpen] = useState(false)
  const budget = config.thinking_budget ?? 0

  return (
    <div className="rounded-lg border border-white/10 bg-black/40">
      <div className="flex items-center gap-3 px-3 py-2">
        <button
          onClick={() => setOpen((o) => !o)}
          className="text-white/50 hover:text-white transition-colors"
          type="button"
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <label className="flex flex-1 items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={config.enabled}
            onChange={(e) => onChange({ enabled: e.target.checked })}
            className="rounded border-white/20 bg-black text-white focus:ring-white/30"
          />
          <div className="flex-1">
            <div className="text-sm font-medium text-white">{title}</div>
            <div className="text-[11px] text-white/50">{description}</div>
          </div>
        </label>
      </div>

      {open && config.enabled && (
        <div className="space-y-3 border-t border-white/5 px-4 pb-3 pt-3">
          {children}

          {supportsThinking && (
            <div>
              <label className="mb-1 block text-[10px] font-medium text-white/50 uppercase tracking-wider">
                Thinking Budget
              </label>
              <div className="flex gap-1">
                {THINKING_BUDGET_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => onChange({ thinking_budget: opt.value === 0 ? 0 : opt.value })}
                    className={clsx(
                      'flex-1 rounded px-2 py-1 text-[11px] transition-colors',
                      budget === opt.value
                        ? 'bg-white text-black'
                        : 'bg-white/[0.04] text-white/70 hover:bg-white/10',
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {config.max_tokens !== undefined && (
            <div>
              <label className="mb-1 block text-[10px] font-medium text-white/50 uppercase tracking-wider">
                Max Output Tokens
              </label>
              <input
                type="number"
                min={100}
                max={20000}
                step={100}
                value={config.max_tokens ?? ''}
                placeholder="default"
                onChange={(e) => {
                  const v = e.target.value.trim()
                  onChange({ max_tokens: v ? Number(v) : null })
                }}
                className="w-full rounded border border-white/10 bg-black px-2 py-1 text-xs text-white focus:border-white/30 focus:outline-none"
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface Props {
  config: PipelineConfig
  onChange: (config: PipelineConfig) => void
  defaults: PipelineDefaultsResponse | null
}

export default function PipelineBuilder({ config, onChange, defaults }: Props) {
  const update = (key: keyof PipelineConfig, partial: Partial<StageConfig>) => {
    onChange({
      ...config,
      [key]: {
        ...(config[key] ?? { enabled: true }),
        ...partial,
      },
    })
  }

  const reset = () => {
    if (defaults?.defaults) onChange(defaults.defaults)
  }

  const agents = defaults?.audience_agents ?? []
  const supportsThinking = defaults?.provider_supports_thinking ?? false

  const voteAgentIds = config.audience_vote?.agent_ids ?? agents.map((a) => a.id)
  const openingAgentIds = config.opening_massacre?.agent_ids ?? agents.map((a) => a.id)

  const expectedCalls = useMemo(
    () => estimateCalls(config, voteAgentIds.length, openingAgentIds.length),
    [config, voteAgentIds.length, openingAgentIds.length],
  )
  const overBudget = expectedCalls > MAX_LLM_CALLS

  const toggleAgent = (stage: 'audience_vote' | 'opening_massacre', agentId: string) => {
    const current = config[stage]?.agent_ids ?? agents.map((a) => a.id)
    const next = current.includes(agentId)
      ? current.filter((id) => id !== agentId)
      : [...current, agentId]
    update(stage, { agent_ids: next })
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-white">Pipeline Builder</div>
          <div className="text-[11px] text-white/50">Toggle stages, tune budgets, pick agents.</div>
        </div>
        <button
          type="button"
          onClick={reset}
          className="flex items-center gap-1 rounded border border-white/10 px-2 py-1 text-[11px] text-white/70 hover:bg-white/10"
          title="Reset to defaults"
        >
          <RotateCcw size={11} /> Reset
        </button>
      </div>

      <div
        className={clsx(
          'mb-3 flex items-center gap-2 rounded-lg px-3 py-2 text-xs',
          overBudget
            ? 'bg-white/10 text-white border border-white/30'
            : 'bg-white/[0.03] text-white/70',
        )}
      >
        {overBudget && <AlertTriangle size={12} />}
        <span>
          Est. <span className="font-mono">{expectedCalls}</span> LLM calls per run
          {overBudget && ` — exceeds ${MAX_LLM_CALLS} cap, request will be rejected`}
        </span>
      </div>

      <div className="space-y-2">
        <StageCard
          title="Generate Variants"
          description={`Create ${config.variants?.n ?? 5} customized drafts`}
          stageKey="variants"
          config={config.variants ?? { enabled: true, n: 5 }}
          onChange={(p) => update('variants', p)}
          supportsThinking={supportsThinking}
        >
          <div>
            <label className="mb-1 block text-[10px] font-medium text-white/50 uppercase tracking-wider">
              Number of variants
            </label>
            <input
              type="number"
              min={1}
              max={10}
              value={config.variants?.n ?? 5}
              onChange={(e) => update('variants', { n: Number(e.target.value) || 5 })}
              className="w-20 rounded border border-white/10 bg-black px-2 py-1 text-xs text-white focus:border-white/30 focus:outline-none"
            />
          </div>
        </StageCard>

        <StageCard
          title="Audience Vote"
          description={`${voteAgentIds.length} of ${agents.length} agents score each variant`}
          stageKey="audience_vote"
          config={config.audience_vote ?? { enabled: true, max_tokens: 800 }}
          onChange={(p) => update('audience_vote', p)}
          supportsThinking={supportsThinking}
        >
          {agents.length > 0 && (
            <div>
              <label className="mb-1 block text-[10px] font-medium text-white/50 uppercase tracking-wider">
                Agents
              </label>
              <div className="flex flex-wrap gap-1">
                {agents.map((a) => {
                  const active = voteAgentIds.includes(a.id)
                  return (
                    <button
                      key={a.id}
                      type="button"
                      onClick={() => toggleAgent('audience_vote', a.id)}
                      className={clsx(
                        'rounded px-2 py-1 text-[11px] transition-colors',
                        active ? 'bg-white text-black' : 'bg-white/[0.04] text-white/70 hover:bg-white/10',
                      )}
                      title={a.description}
                    >
                      {a.name}
                    </button>
                  )
                })}
              </div>
            </div>
          )}
        </StageCard>

        <StageCard
          title="Refine"
          description={`Rewrite top ${config.refine?.top_k ?? 2} using audience feedback`}
          stageKey="refine"
          config={config.refine ?? { enabled: true, top_k: 2 }}
          onChange={(p) => update('refine', p)}
          supportsThinking={supportsThinking}
        >
          <div>
            <label className="mb-1 block text-[10px] font-medium text-white/50 uppercase tracking-wider">
              Top K
            </label>
            <input
              type="number"
              min={1}
              max={config.variants?.n ?? 5}
              value={config.refine?.top_k ?? 2}
              onChange={(e) => update('refine', { top_k: Number(e.target.value) || 1 })}
              className="w-20 rounded border border-white/10 bg-black px-2 py-1 text-xs text-white focus:border-white/30 focus:outline-none"
            />
            <div className="mt-1 text-[10px] text-white/40">
              Capped at num_variants. Only runs when Audience Vote is enabled.
            </div>
          </div>
        </StageCard>

        <StageCard
          title="Opening Massacre"
          description={`Generate ${config.opening_massacre?.n ?? 10} hooks, audience picks winner`}
          stageKey="opening_massacre"
          config={config.opening_massacre ?? { enabled: true, n: 10, max_tokens: 400 }}
          onChange={(p) => update('opening_massacre', p)}
          supportsThinking={supportsThinking}
        >
          <div>
            <label className="mb-1 block text-[10px] font-medium text-white/50 uppercase tracking-wider">
              Openings to generate
            </label>
            <input
              type="number"
              min={3}
              max={15}
              value={config.opening_massacre?.n ?? 10}
              onChange={(e) => update('opening_massacre', { n: Number(e.target.value) || 10 })}
              className="w-20 rounded border border-white/10 bg-black px-2 py-1 text-xs text-white focus:border-white/30 focus:outline-none"
            />
          </div>
          {agents.length > 0 && (
            <div>
              <label className="mb-1 block text-[10px] font-medium text-white/50 uppercase tracking-wider">
                Scoring agents
              </label>
              <div className="flex flex-wrap gap-1">
                {agents.map((a) => {
                  const active = openingAgentIds.includes(a.id)
                  return (
                    <button
                      key={a.id}
                      type="button"
                      onClick={() => toggleAgent('opening_massacre', a.id)}
                      className={clsx(
                        'rounded px-2 py-1 text-[11px] transition-colors',
                        active ? 'bg-white text-black' : 'bg-white/[0.04] text-white/70 hover:bg-white/10',
                      )}
                      title={a.description}
                    >
                      {a.name}
                    </button>
                  )
                })}
              </div>
            </div>
          )}
        </StageCard>

        <StageCard
          title="Humanize"
          description="Strip AI tells, apply founder voice + vocab"
          stageKey="humanize"
          config={config.humanize ?? { enabled: true }}
          onChange={(p) => update('humanize', p)}
          supportsThinking={supportsThinking}
        />

        <StageCard
          title="Quality Gate"
          description="Final automated checks (slop detection, cliché filter)"
          stageKey="quality_gate"
          config={config.quality_gate ?? { enabled: true }}
          onChange={(p) => update('quality_gate', p)}
          supportsThinking={false}
        />
      </div>
    </div>
  )
}
