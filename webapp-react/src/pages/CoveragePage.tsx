import { useQuery } from '@tanstack/react-query'
import { Loader2, Lightbulb } from 'lucide-react'
import clsx from 'clsx'
import { apiGet } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import type { CoverageData } from '../types/api'

function heatColor(value: number): string {
  if (value >= 0.8) return 'bg-white/20'
  if (value >= 0.6) return 'bg-green-700'
  if (value >= 0.4) return 'bg-white/20'
  if (value >= 0.2) return 'bg-white'
  if (value > 0) return 'bg-white/10'
  return 'bg-gray-800'
}

export default function CoveragePage() {
  const active = useFounderStore((s) => s.active)

  const { data: coverage, isLoading } = useQuery<CoverageData>({
    queryKey: ['coverage', active],
    queryFn: () => apiGet(`/api/coverage/${active}`),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={24} className="animate-spin text-gray-400" />
      </div>
    )
  }

  if (!coverage) {
    return <p className="py-8 text-center text-gray-400">No coverage data available.</p>
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Graph Coverage</h2>

      {/* Overall progress */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium text-gray-300">Overall Coverage</span>
          <span className="text-sm font-semibold text-gray-100">
            {(coverage.overall_pct * 100).toFixed(1)}%
          </span>
        </div>
        <div className="h-3 overflow-hidden rounded-full bg-gray-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-white to-white transition-all"
            style={{ width: `${coverage.overall_pct * 100}%` }}
          />
        </div>
        <p className="mt-1 text-xs text-gray-500">
          {coverage.covered_nodes} / {coverage.total_nodes} nodes covered
        </p>
      </div>

      {/* Per-type bars */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(coverage.by_type).map(([type, data]) => (
          <div
            key={type}
            className="rounded-xl border border-gray-800 bg-gray-900 p-4"
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-400 capitalize">
                {type.replace('_', ' ')}
              </span>
              <span className="text-xs font-semibold text-gray-200">
                {(data.pct * 100).toFixed(0)}%
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-gray-800">
              <div
                className="h-full rounded-full bg-white"
                style={{ width: `${data.pct * 100}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-gray-500">
              {data.covered} / {data.total}
            </p>
          </div>
        ))}
      </div>

      {/* Heatmap */}
      {Object.keys(coverage.heatmap).length > 0 && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <h3 className="mb-3 text-sm font-semibold text-gray-300">
            Coverage Heatmap
          </h3>
          <div className="flex flex-wrap gap-1">
            {Object.entries(coverage.heatmap).map(([nodeId, value]) => (
              <div
                key={nodeId}
                className={clsx(
                  'h-6 w-6 rounded-sm transition-colors',
                  heatColor(value),
                )}
                title={`${nodeId}: ${(value * 100).toFixed(0)}%`}
              />
            ))}
          </div>
        </div>
      )}

      {/* Opportunities */}
      {coverage.opportunities.length > 0 && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-300">
            <Lightbulb size={16} className="text-white" />
            Untouched Opportunities
          </h3>
          <div className="space-y-1.5">
            {coverage.opportunities.map((opp) => (
              <div
                key={opp.node_id}
                className="flex items-center gap-2 rounded-lg bg-gray-800 px-3 py-2 text-sm"
              >
                <span className="rounded-full bg-gray-700 px-2 py-0.5 text-xs text-gray-400 capitalize">
                  {opp.node_type.replace('_', ' ')}
                </span>
                <span className="text-gray-200">{opp.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
