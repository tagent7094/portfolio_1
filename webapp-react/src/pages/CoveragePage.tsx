import { useQuery } from '@tanstack/react-query'
import { Lightbulb, BarChart3 } from 'lucide-react'
import clsx from 'clsx'
import { apiGet } from '../api/client'
import { useFounderStore } from '../store/useFounderStore'
import { PageHeader, Card, CardHeader, CardBody, CardTitle, Badge, Spinner, EmptyState } from '../components/ui'
import type { CoverageData } from '../types/api'

function heatColor(value: number): string {
  if (value >= 0.8) return 'bg-[var(--success)] opacity-90'
  if (value >= 0.6) return 'bg-[var(--success)] opacity-60'
  if (value >= 0.4) return 'bg-[var(--warning)] opacity-50'
  if (value >= 0.2) return 'bg-[var(--warning)] opacity-30'
  if (value > 0)   return 'bg-white/10'
  return 'bg-[var(--surface-4)]'
}

export default function CoveragePage() {
  const active = useFounderStore((s) => s.active)

  const { data: coverage, isLoading } = useQuery<CoverageData>({
    queryKey: ['coverage', active],
    queryFn: () => apiGet(`/api/coverage/${active}`),
  })

  if (isLoading) return <Spinner fullPage />
  if (!coverage) return (
    <EmptyState
      icon={<BarChart3 size={22} />}
      title="No coverage data"
      description="Run the ingest pipeline first to generate coverage stats."
    />
  )

  const pct = Math.round(coverage.overall_pct * 100)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Graph Coverage"
        subtitle={`${coverage.covered_nodes} of ${coverage.total_nodes} nodes covered`}
      />

      {/* Overall progress */}
      <Card className="animate-slide-up">
        <CardBody>
          <div className="mb-3 flex items-center justify-between">
            <span className="text-[13px] font-semibold text-[var(--text-secondary)]">Overall Coverage</span>
            <span className="font-[var(--font-display)] text-[22px] font-bold text-[var(--text-primary)]">{pct}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--surface-4)]">
            <div
              className="h-full rounded-full bg-white transition-all duration-700"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="mt-2 text-[12px] text-[var(--text-muted)]">
            {coverage.covered_nodes} / {coverage.total_nodes} nodes covered
          </p>
        </CardBody>
      </Card>

      {/* Per-type */}
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
        {Object.entries(coverage.by_type).map(([type, data], i) => {
          const p = Math.round(data.pct * 100)
          return (
            <Card key={type} className="animate-slide-up p-4" style={{ animationDelay: `${i * 60}ms` }}>
              <div className="mb-3 flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)] capitalize">
                  {type.replace('_', ' ')}
                </span>
                <span className="text-[13px] font-bold text-[var(--text-primary)]">{p}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-4)]">
                <div className="h-full rounded-full bg-white" style={{ width: `${p}%` }} />
              </div>
              <p className="mt-2 text-[11px] text-[var(--text-muted)]">{data.covered}/{data.total}</p>
            </Card>
          )
        })}
      </div>

      {/* Heatmap */}
      {Object.keys(coverage.heatmap).length > 0 && (
        <Card className="animate-slide-up stagger-3">
          <CardHeader>
            <CardTitle>Coverage Heatmap</CardTitle>
            <div className="flex items-center gap-2 text-[11px] text-[var(--text-muted)]">
              <span className="h-2.5 w-2.5 rounded-sm bg-[var(--surface-4)] inline-block" /> Low
              <span className="h-2.5 w-2.5 rounded-sm bg-[var(--warning)]/40 inline-block" /> Mid
              <span className="h-2.5 w-2.5 rounded-sm bg-[var(--success)]/80 inline-block" /> High
            </div>
          </CardHeader>
          <CardBody>
            <div className="flex flex-wrap gap-1">
              {Object.entries(coverage.heatmap).map(([nodeId, value]) => (
                <div
                  key={nodeId}
                  className={clsx('h-5 w-5 rounded-sm transition-colors cursor-default', heatColor(value))}
                  title={`${nodeId}: ${Math.round((value as number) * 100)}%`}
                />
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {/* Opportunities */}
      {coverage.opportunities.length > 0 && (
        <Card className="animate-slide-up stagger-4">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Lightbulb size={15} className="text-[var(--warning)]" />
              <CardTitle>Untouched Opportunities</CardTitle>
            </div>
            <Badge variant="warning">{coverage.opportunities.length}</Badge>
          </CardHeader>
          <CardBody className="pt-2">
            <div className="space-y-1.5">
              {coverage.opportunities.map((opp) => (
                <div
                  key={opp.node_id}
                  className="flex items-center gap-3 rounded-lg bg-[var(--surface-3)] px-3.5 py-2.5"
                >
                  <Badge variant="default">
                    {opp.node_type.replace('_', ' ')}
                  </Badge>
                  <span className="text-[13px] text-[var(--text-primary)]">{opp.label}</span>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
