import ModelsConfigPanel from '../components/config/ModelsConfigPanel'
import { PageHeader } from '../components/ui'
import { useFounderStore } from '../store/useFounderStore'

export default function ConfigPage() {
  const activeFounder = useFounderStore((s) => s.active)

  return (
    <div className="space-y-6 max-w-2xl">
      <PageHeader
        title="Configuration"
        subtitle={`LLM providers and per-task model assignments for ${activeFounder}`}
      />

      {activeFounder ? (
        <ModelsConfigPanel mode="founder" founderSlug={activeFounder} />
      ) : (
        <div className="text-[12px] text-[var(--text-muted)]">
          No active founder — select a founder first.
        </div>
      )}
    </div>
  )
}
