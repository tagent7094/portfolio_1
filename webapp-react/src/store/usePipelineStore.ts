import { create } from 'zustand'
import type { PipelineEvent, PostVariant, AgentVote, AggregatedScore, OpeningLine, GenerationResult } from '../types/api'

type StepState = 'pending' | 'active' | 'completed'

interface PipelineState {
  // Status
  running: boolean
  error: string | null
  stepStates: Record<string, StepState>

  // Stage 1: Posts
  posts: PostVariant[]
  streamingTokens: Record<string, string>

  // Stage 2: Votes
  votes: Record<string, Record<string, AgentVote>>
  agentNames: Record<string, string>
  aggregated: Record<string, AggregatedScore>
  topIds: string[]

  // Stage 3: Refinement
  refinedPosts: any[]

  // Stage 4: Opening Massacre
  openingLines: OpeningLine[]
  openingVotes: Record<string, Record<string, AgentVote>>
  winningOpening: OpeningLine | null

  // Stage 5: Final
  result: GenerationResult | null

  // Actions
  reset: () => void
  setRunning: (running: boolean) => void
  handleEvent: (event: PipelineEvent) => void
}

const STEP_MAP: Record<string, string> = {
  match_topic: 'generate',
  generate_all_posts: 'generate',
  audience_vote: 'vote',
  select_top: 'vote',
  refine_posts: 'refine',
  select_final: 'refine',
  opening_massacre: 'massacre',
  humanize: 'humanize',
  quality_gate: 'humanize',
  track_coverage: 'humanize',
}

export const usePipelineStore = create<PipelineState>((set, get) => ({
  running: false,
  error: null,
  stepStates: {},
  posts: [],
  streamingTokens: {},
  votes: {},
  agentNames: {},
  aggregated: {},
  topIds: [],
  refinedPosts: [],
  openingLines: [],
  openingVotes: {},
  winningOpening: null,
  result: null,

  reset: () => set({
    running: false,
    error: null,
    stepStates: {},
    posts: [],
    streamingTokens: {},
    votes: {},
    agentNames: {},
    aggregated: {},
    topIds: [],
    refinedPosts: [],
    openingLines: [],
    openingVotes: {},
    winningOpening: null,
    result: null,
  }),

  setRunning: (running) => set({ running }),

  handleEvent: (event) => {
    const { stage, status, data } = event
    const stepKey = STEP_MAP[stage] || stage

    set((s) => {
      const newSteps = { ...s.stepStates }

      if (status === 'started' || status === 'generating' || status === 'voting') {
        newSteps[stepKey] = 'active'
      } else if (status === 'completed') {
        newSteps[stepKey] = 'completed'
      }

      const updates: Partial<PipelineState> = { stepStates: newSteps }

      // Stage-specific updates
      switch (stage) {
        case 'generate_all_posts':
          if (status === 'started') {
            updates.posts = []
            updates.streamingTokens = {}
          }
          if (status === 'progress' && data?.post) {
            updates.posts = [...s.posts, data.post]
          }
          break

        case 'llm_token':
          if (data?.token && data?.engine_id) {
            updates.streamingTokens = {
              ...s.streamingTokens,
              [data.engine_id]: (s.streamingTokens[data.engine_id] || '') + data.token,
            }
          }
          break

        case 'audience_vote':
          if (status === 'progress' && data?.votes) {
            updates.votes = { ...s.votes, [data.agent_id]: data.votes }
            updates.agentNames = { ...s.agentNames, [data.agent_id]: data.agent_name }
          }
          if (status === 'completed' && data?.top_ids) {
            updates.topIds = data.top_ids
            updates.aggregated = data.aggregated || {}
          }
          break

        case 'refine_posts':
          if (status === 'progress') {
            updates.refinedPosts = [...s.refinedPosts, data]
          }
          break

        case 'opening_massacre':
          if (status === 'generating' && data?.openings) {
            updates.openingLines = data.openings
          }
          if (status === 'voting' && data?.votes) {
            updates.openingVotes = { ...s.openingVotes, [data.agent_id]: data.votes }
          }
          if (status === 'completed' && data?.winning_text) {
            updates.winningOpening = { id: 'winner', text: data.winning_text, strategy: '' }
          }
          break

        case 'done':
          if (data?.error) {
            updates.error = data.error
          } else {
            updates.result = data
          }
          updates.running = false
          break

        case 'error':
          updates.error = data?.error || 'Pipeline failed'
          updates.running = false
          break
      }

      return updates
    })
  },
}))
