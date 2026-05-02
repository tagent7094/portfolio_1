import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Network, GitBranch, Brain, BookOpen, Palette, Lightbulb, Upload, Zap, BarChart3, Cpu } from 'lucide-react'
import { apiGet, apiPost } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import { PageHeader, StatCard, Card, CardHeader, CardBody, CardTitle, Button, EmptyState } from '../components/ui'
import type { GraphStats } from '../types/api'

const STAT_ICONS = [Network, GitBranch, Brain, BookOpen, Palette, Lightbulb] as const

export default function DashboardPage() {
  const active = useFounderStore((s) => s.active)
  const queryClient = useQueryClient()
  const [ingesting, setIngesting] = useState(false)
  const [buildingViral, setBuildingViral] = useState<null | 'stat' | 'llm'>(null)

  const { data: stats } = useQuery<GraphStats>({
    queryKey: ['graph-stats', active],
    queryFn: () => apiGet('/api/graph/stats'),
  })
  const { data: viralStats } = useQuery<GraphStats>({
    queryKey: ['viral-graph-stats'],
    queryFn: () => apiGet('/api/viral-graph/stats'),
  })
  const { data: card } = useQuery<{ card: string }>({
    queryKey: ['personality-card', active],
    queryFn: () => apiGet('/api/graph/personality-card'),
  })

  const handleIngest = async () => {
    setIngesting(true)
    try {
      await apiPost('/api/ingest')
      queryClient.invalidateQueries({ queryKey: ['graph-stats'] })
      queryClient.invalidateQueries({ queryKey: ['personality-card'] })
    } catch (e) { console.error('Ingest failed:', e) }
    finally { setIngesting(false) }
  }

  const handleBuildViral = async (useLlm: boolean) => {
    setBuildingViral(useLlm ? 'llm' : 'stat')
    try {
      await apiPost<{ nodes: number; edges: number; posts_parsed: number }>(
        `/api/ingest/viral?use_llm=${useLlm}`
      )
      queryClient.invalidateQueries({ queryKey: ['viral-graph-stats'] })
    } catch (e) { console.error('Viral build failed:', e) }
    finally { setBuildingViral(null) }
  }

  const statCards = stats
    ? [
        { label: 'Nodes',       value: stats.nodes },
        { label: 'Edges',       value: stats.edges },
        { label: 'Beliefs',     value: stats.types?.belief ?? 0 },
        { label: 'Stories',     value: stats.types?.story ?? 0 },
        { label: 'Style rules', value: stats.types?.style_rule ?? 0 },
        { label: 'Models',      value: stats.types?.thinking_model ?? 0 },
      ]
    : []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        subtitle="Overview of your knowledge graph and content stats"
        actions={
          <Button
            onClick={handleIngest}
            loading={ingesting}
            icon={<Upload size={14} />}
            size="sm"
          >
            {ingesting ? 'Ingesting…' : 'Ingest data'}
          </Button>
        }
      />

      {/* Stat cards */}
      {statCards.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {statCards.map(({ label, value }, i) => {
            const Icon = STAT_ICONS[i]
            return (
              <StatCard
                key={label}
                icon={<Icon size={15} />}
                label={label}
                value={value}
                animationDelay={i * 50}
              />
            )
          })}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {STAT_ICONS.map((_Icon, i) => (
            <div key={i} className="card animate-pulse p-4 space-y-3">
              <div className="h-3 w-12 rounded bg-[var(--surface-4)]" />
              <div className="h-7 w-8 rounded bg-[var(--surface-4)]" />
            </div>
          ))}
        </div>
      )}

      {/* Viral Brain */}
      <Card className="animate-slide-up stagger-3">
        <CardHeader>
          <div className="flex items-center gap-2.5">
            <Zap size={17} className="text-[var(--warning)]" />
            <CardTitle>Viral Posts Brain</CardTitle>
          </div>
          {viralStats && !viralStats.empty && (
            <div className="flex items-center gap-4">
              {[
                { v: viralStats.nodes, label: 'nodes' },
                { v: viralStats.edges, label: 'edges' },
                viralStats.types?.hook_type ? { v: viralStats.types.hook_type, label: 'hooks' } : null,
                viralStats.types?.structure_template ? { v: viralStats.types.structure_template, label: 'structures' } : null,
              ].filter(Boolean).map((item: any) => (
                <div key={item.label} className="text-center">
                  <p className="text-[18px] font-bold leading-none text-[var(--text-primary)]">{item.v}</p>
                  <p className="mt-0.5 text-[10px] uppercase tracking-widest text-[var(--text-muted)]">{item.label}</p>
                </div>
              ))}
            </div>
          )}
        </CardHeader>
        <CardBody>
          <p className="mb-4 text-[13px] text-[var(--text-secondary)]">
            Knowledge graph extracted from {viralStats?.empty === false ? 'your' : '1,400+'} viral LinkedIn posts —
            used to inform post structure, hooks, and engagement patterns.
          </p>
          <div className="flex flex-wrap gap-2.5">
            <Button
              variant="primary"
              size="sm"
              onClick={() => handleBuildViral(false)}
              disabled={buildingViral !== null}
              loading={buildingViral === 'stat'}
              icon={<BarChart3 size={14} />}
            >
              {buildingViral === 'stat' ? 'Building…' : 'Statistical build'}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => handleBuildViral(true)}
              disabled={buildingViral !== null}
              loading={buildingViral === 'llm'}
              icon={<Cpu size={14} />}
            >
              {buildingViral === 'llm' ? 'Building with LLM…' : 'Full build (+ LLM)'}
            </Button>
            <span className="flex items-center text-[12px] text-[var(--text-muted)]">
              {viralStats?.empty === false
                ? `Last built · ${viralStats.nodes} nodes`
                : 'Statistical ~5s · Full with LLM takes minutes'}
            </span>
          </div>
        </CardBody>
      </Card>

      {/* Personality Card */}
      {card?.card && (
        <Card className="animate-slide-up stagger-4">
          <CardHeader>
            <CardTitle>Personality Card</CardTitle>
          </CardHeader>
          <CardBody>
            <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
              {card.card}
            </p>
          </CardBody>
        </Card>
      )}

      {!stats && !card?.card && (
        <EmptyState
          icon={<Network size={22} />}
          title="No graph data yet"
          description="Click 'Ingest data' to build your knowledge graph from your LinkedIn posts."
        />
      )}
    </div>
  )
}
