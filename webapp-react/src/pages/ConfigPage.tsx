import ModelsConfigPanel from '../components/config/ModelsConfigPanel'
import { PageHeader } from '../components/ui'
import { useAuthStore } from '../store/useAuthStore'

export default function ConfigPage() {
  const slug = useAuthStore((s) => s.slug)

  return (
    <div className="space-y-6 max-w-2xl">
      <PageHeader
        title="Configuration"
        subtitle="Configure LLM providers and per-task model assignments"
      />

      {slug ? (
        <ModelsConfigPanel mode="founder" founderSlug={slug} />
      ) : (
        <div className="text-[12px] text-[var(--text-muted)]">
          Founder slug not detected — per-task overrides are only available on a founder portal.
        </div>
      )}
    </div>
  )
}
