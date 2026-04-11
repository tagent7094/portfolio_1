// ── Founders ──
export interface Founder {
  slug: string
  display_name: string
  active: boolean
  has_graph: boolean
}

// ── Graph ──
export interface GraphNode {
  id: string
  type: string
  label: string
  [key: string]: any
}

export interface GraphEdge {
  source: string
  target: string
  type: string
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface GraphStats {
  empty: boolean
  nodes: number
  edges: number
  types: Record<string, number>
  personality_card_words?: number
}

// ── Pipeline Events (SSE) ──
export interface PipelineEvent {
  stage: string
  status: string
  data: any
  progress: number
  agent_id: string
}

export interface PostVariant {
  id: string
  text: string
  engine_id: string
  engine_name: string
  platform: string
}

export interface AgentVote {
  score: number
  feedback: string
}

export interface AggregatedScore {
  mean: number
  scores_by_agent: Record<string, number>
  feedback_by_agent?: Record<string, string>
}

export interface OpeningLine {
  id: string
  text: string
  strategy: string
}

// ── Generation Request/Response ──
export interface TopicRequest {
  topic: string
  platform: string
  creativity: number
  founder_slug?: string
}

export interface GenerationResult {
  post: string
  quality: { passed: boolean; score: number; checks?: Record<string, boolean> }
  influence: {
    overall: number
    belief_alignment: { score: number; matched?: any[] }
    story_influence: { score: number; matched?: any[] }
    style_adherence: { score: number; matched?: any[] }
    personality_alignment?: number
  }
  all_posts: PostVariant[]
  audience_votes: Record<string, Record<string, AgentVote>>
  aggregated_scores: Record<string, AggregatedScore>
  top_post_ids: string[]
  refined_posts: any[]
  opening_lines?: OpeningLine[]
  opening_votes?: any
  winning_opening?: OpeningLine
  agent_log: any[]
  filename?: string
}

// ── Coverage ──
export interface CoverageData {
  overall_pct: number
  total_nodes: number
  covered_nodes: number
  by_type: Record<string, { covered: number; total: number; pct: number }>
  heatmap: Record<string, number>
  opportunities: Array<{ node_id: string; node_type: string; label: string }>
}

// ── Config ──
export interface LLMConfig {
  llm: {
    provider: string
    model: string
    base_url?: string
    api_key?: string
    temperature?: number
    max_tokens?: number
    enable_thinking?: boolean
    effort?: string
  }
  embedding: { model: string }
  founders: {
    active: string
    registry: Record<string, any>
  }
}

// ── Workflow ──
export interface WorkflowNodeType {
  id: string
  label: string
  inputs: number
  outputs: number
  executor?: string
  description?: string
}

// ── Post Customizer ──
export interface ViralPost {
  post_id: string
  content: string
  likes: number
  comments: number
  reposts: number
  followers: number
  likes_ratio: number
  engagement_score: number
  content_type: string
  creator_url: string
}

export interface PostBrowseResult {
  posts: ViralPost[]
  total: number
  page: number
  pages: number
}

export interface TraceabilityNode {
  node_id: string
  topic?: string
  stance?: string
  title?: string
  rule_type?: string
  description?: string
}

export interface Traceability {
  belief_nodes: TraceabilityNode[]
  story_nodes: TraceabilityNode[]
  style_rule_nodes: TraceabilityNode[]
  vocabulary_phrases_used: number
  vocabulary_phrases_never: number
}

export interface CustomizationResult {
  original: string
  customized: string
  sections: Record<string, { original: string; customized: string }>
  topic: string
  founder_context: any
  viral_context: any
  traceability?: Traceability
  all_variants?: { id: string; engine_name: string; strategy?: string; text: string; quality?: number; word_count?: number }[]
  is_collection?: boolean
  quality?: { score: number; passed: boolean }
  // V2 Adaptation fields
  founder_internalization?: FounderInternalization
  source_dissection?: SourceDissection
  events_used?: string[]
  v2_quality?: V2QualityResult[]
}

// ── V2 Adaptation ──
export interface FounderInternalization {
  tensions: string[]
  signature_scenes: string[]
  argument_rhythm: string
  vulnerable_moments: string[]
  recurring_cast: string[]
  word_count_range: [number, number]
  key_moments_inventory: string[]
}

export interface SourceDissection {
  narrative_arc: string
  hook_mechanics: Array<{ sentence: string; structural_function: string; rhythm: string }>
  sentence_count: number
  body_structure: string
  ending_type: string
  virality_reason?: string
}

export interface V2QualityResult {
  post_id: string
  quality: {
    checks: Record<string, boolean>
    passed: boolean
    failures_count: number
    failed_checks?: string[]
    rewrite_suggestions?: string[]
    word_count_actual?: number
  }
}

// ── Workflow ──
export interface WorkflowConfig {
  id: string
  name: string
  nodes: Array<{
    id: string
    type: string
    position: { x: number; y: number }
    data: { label: string; prompt?: string; config?: Record<string, any> }
  }>
  edges: Array<{ id: string; source: string; target: string }>
}
