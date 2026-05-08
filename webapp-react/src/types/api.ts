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

