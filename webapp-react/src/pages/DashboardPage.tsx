import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Network,
  GitBranch,
  Brain,
  BookOpen,
  Palette,
  Lightbulb,
  Upload,
  Loader2,
  Zap,
  BarChart3,
  Cpu,
} from 'lucide-react'
import { apiGet, apiPost } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import type { GraphStats } from '../types/api'

const STAT_ICONS = [Network, GitBranch, Brain, BookOpen, Palette, Lightbulb] as const

export default function DashboardPage() {
  const active = useFounderStore((s) => s.active)
  const queryClient = useQueryClient()
  const [ingesting, setIngesting] = useState(false)
  const [buildingViral, setBuildingViral] = useState<string | null>(null) // null | 'stat' | 'llm'

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
    } catch (e) {
      console.error('Ingest failed:', e)
    } finally {
      setIngesting(false)
    }
  }

  const handleBuildViral = async (useLlm: boolean) => {
    setBuildingViral(useLlm ? 'llm' : 'stat')
    try {
      const result = await apiPost<{ nodes: number; edges: number; posts_parsed: number }>(
        `/api/ingest/viral?use_llm=${useLlm}`
      )
      console.log('[Viral] Built:', result)
      queryClient.invalidateQueries({ queryKey: ['viral-graph-stats'] })
    } catch (e) {
      console.error('Viral build failed:', e)
    } finally {
      setBuildingViral(null)
    }
  }

  const statCards = stats
    ? [
        { label: 'Nodes', value: stats.nodes },
        { label: 'Edges', value: stats.edges },
        { label: 'Beliefs', value: stats.types?.belief ?? 0 },
        { label: 'Stories', value: stats.types?.story ?? 0 },
        { label: 'Style Rules', value: stats.types?.style_rule ?? 0 },
        { label: 'Models', value: stats.types?.thinking_model ?? 0 },
      ]
    : []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <button
          onClick={handleIngest}
          disabled={ingesting}
          className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-black transition-colors hover:bg-white disabled:opacity-50"
        >
          {ingesting ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
          {ingesting ? 'Ingesting...' : 'Ingest Founder Data'}
        </button>
      </div>

      {/* Founder Graph Stats */}
      <div>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-400">
          Founder Knowledge Graph
        </h3>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {statCards.map(({ label, value }, i) => {
            const Icon = STAT_ICONS[i]
            return (
              <div key={label} className="rounded-xl border border-gray-800 bg-gray-900 p-4">
                <div className="mb-2 flex items-center gap-2 text-gray-400">
                  <Icon size={16} />
                  <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
                </div>
                <p className="text-2xl font-bold text-gray-100">{value}</p>
              </div>
            )
          })}
        </div>
      </div>

      {/* Viral Graph Section */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-semibold text-gray-100">
              <Zap size={20} className="text-white" />
              Viral Posts Brain
            </h3>
            <p className="mt-1 text-sm text-gray-400">
              Knowledge graph extracted from {viralStats?.empty === false ? 'your' : '1,400+'} viral LinkedIn posts.
              Used to inform post structure, hooks, and engagement patterns.
            </p>
          </div>

          {/* Viral stats badges */}
          {viralStats && !viralStats.empty && (
            <div className="flex gap-3">
              <div className="text-center">
                <p className="text-lg font-bold text-white">{viralStats.nodes}</p>
                <p className="text-[10px] uppercase text-gray-500">nodes</p>
              </div>
              <div className="text-center">
                <p className="text-lg font-bold text-white">{viralStats.edges}</p>
                <p className="text-[10px] uppercase text-gray-500">edges</p>
              </div>
              {viralStats.types?.hook_type && (
                <div className="text-center">
                  <p className="text-lg font-bold text-white">{viralStats.types.hook_type}</p>
                  <p className="text-[10px] uppercase text-gray-500">hooks</p>
                </div>
              )}
              {viralStats.types?.structure_template && (
                <div className="text-center">
                  <p className="text-lg font-bold text-white">{viralStats.types.structure_template}</p>
                  <p className="text-[10px] uppercase text-gray-500">structures</p>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-3">
          <button
            onClick={() => handleBuildViral(false)}
            disabled={buildingViral !== null}
            className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-black transition-colors hover:bg-white disabled:opacity-50"
          >
            {buildingViral === 'stat' ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <BarChart3 size={16} />
            )}
            {buildingViral === 'stat' ? 'Building...' : 'Build Graph (Statistical Only)'}
          </button>

          <button
            onClick={() => handleBuildViral(true)}
            disabled={buildingViral !== null}
            className="flex items-center gap-2 rounded-lg border border-white/30 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-white/10 disabled:opacity-50"
          >
            {buildingViral === 'llm' ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Cpu size={16} />
            )}
            {buildingViral === 'llm' ? 'Building with LLM...' : 'Build Full Graph (Statistical + LLM)'}
          </button>

          <p className="flex items-center text-xs text-gray-500">
            {viralStats?.empty === false
              ? `Last built: ${viralStats.nodes} nodes`
              : 'Not built yet — statistical takes ~5s, full with LLM takes minutes'}
          </p>
        </div>
      </div>

      {/* Personality Card */}
      {card?.card && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
          <h3 className="mb-3 text-lg font-semibold text-gray-100">Personality Card</h3>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-300">
            {card.card}
          </p>
        </div>
      )}
    </div>
  )
}
