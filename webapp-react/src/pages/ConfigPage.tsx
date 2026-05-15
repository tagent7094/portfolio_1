import { useEffect, useState } from 'react'
import { Save, CheckCircle2, Cpu, Database } from 'lucide-react'
import { apiGet, apiPost } from '../api/client'
import type { LLMConfig } from '../types/api'
import { PageHeader, Card, CardHeader, CardBody, CardTitle, Button, Spinner } from '../components/ui'
import ModelsConfigPanel from '../components/config/ModelsConfigPanel'
import { useAuthStore } from '../store/useAuthStore'

const PROVIDERS = ['anthropic', 'openai', 'gemini', 'nvidia', 'openrouter', 'lmstudio', 'ollama'] as const

interface ProviderDefaults { base_url: string; default_model: string; models: string[]; has_api_key: boolean }

interface LLMSectionProps {
  title: string
  icon: React.ReactNode
  provider: string; model: string; apiKey: string
  providerDefaults: Record<string, ProviderDefaults>
  onProviderChange: (p: string) => void
  onModelChange: (m: string) => void
  onApiKeyChange: (k: string) => void
}

function LLMSection({ title, icon, provider, model, apiKey, providerDefaults, onProviderChange, onModelChange, onApiKeyChange }: LLMSectionProps) {
  const defaults = providerDefaults[provider]
  const models = defaults?.models || []
  const isLocal = provider === 'lmstudio' || provider === 'ollama'

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          {icon}
          <CardTitle>{title}</CardTitle>
        </div>
        {defaults?.base_url && (
          <code className="rounded-md bg-[var(--surface-3)] px-2 py-0.5 text-[11px] text-[var(--text-muted)]">
            {defaults.base_url}
          </code>
        )}
      </CardHeader>
      <CardBody className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Provider */}
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Provider</label>
            <select
              value={provider}
              onChange={(e) => {
                const p = e.target.value
                onProviderChange(p)
                const d = providerDefaults[p]
                if (d) onModelChange(d.default_model)
              }}
              className="field"
            >
              {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>

          {/* Model */}
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Model</label>
            {models.length > 0 ? (
              <div className="flex gap-2">
                <select
                  value={models.includes(model) ? model : ''}
                  onChange={(e) => onModelChange(e.target.value)}
                  className="field flex-1"
                >
                  {models.map((m) => <option key={m} value={m}>{m}</option>)}
                  {!models.includes(model) && model && <option value={model}>{model} (custom)</option>}
                </select>
                <input
                  type="text"
                  value={model}
                  onChange={(e) => onModelChange(e.target.value)}
                  placeholder="custom…"
                  className="field w-32"
                />
              </div>
            ) : (
              <input
                type="text"
                value={model}
                onChange={(e) => onModelChange(e.target.value)}
                placeholder={isLocal ? 'e.g. ibm/granite-4-h-tiny' : 'Model name'}
                className="field"
              />
            )}
          </div>
        </div>

        {!isLocal && (
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
              API Key
              {defaults?.has_api_key && (
                <span className="ml-2 rounded-full bg-[var(--success-dim)] px-2 py-0.5 text-[10px] text-[var(--success)]">
                  loaded from .env
                </span>
              )}
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => onApiKeyChange(e.target.value)}
              placeholder={defaults?.has_api_key ? '••• loaded from .env •••' : 'Paste API key…'}
              className="field"
            />
          </div>
        )}
      </CardBody>
    </Card>
  )
}

export default function ConfigPage() {
  const [genProvider, setGenProvider] = useState('anthropic')
  const [genModel, setGenModel] = useState('')
  const [genApiKey, setGenApiKey] = useState('')
  const [ingProvider, setIngProvider] = useState('lmstudio')
  const [ingModel, setIngModel] = useState('')
  const [ingApiKey, setIngApiKey] = useState('')
  const [providerDefaults, setProviderDefaults] = useState<Record<string, ProviderDefaults>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    Promise.all([
      apiGet<LLMConfig>('/api/config'),
      apiGet<Record<string, ProviderDefaults>>('/api/config/providers'),
    ]).then(([cfg, defaults]) => {
      setGenProvider(cfg.llm.provider); setGenModel(cfg.llm.model); setGenApiKey(cfg.llm.api_key ?? '')
      const ing = (cfg as any).llm_ingestion
      if (ing) { setIngProvider(ing.provider || 'lmstudio'); setIngModel(ing.model || ''); setIngApiKey(ing.api_key ?? '') }
      setProviderDefaults(defaults); setLoaded(true)
    })
  }, [])

  const handleSave = async () => {
    setSaving(true); setSaved(false)
    try {
      await Promise.all([
        apiPost('/api/config', { provider: genProvider, model: genModel, api_key: genApiKey || undefined }),
        apiPost('/api/config/ingestion', { provider: ingProvider, model: ingModel, api_key: ingApiKey || undefined }),
      ])
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) { console.error('[Config] Save failed:', e) }
    finally { setSaving(false) }
  }

  const slug = useAuthStore((s) => s.slug)

  if (!loaded) return <Spinner fullPage />

  return (
    <div className="space-y-6 max-w-2xl">
      <PageHeader
        title="Configuration"
        subtitle="Set LLM providers for post generation and knowledge graph ingestion"
      />

      <LLMSection
        title="Post Generation"
        icon={<Cpu size={15} className="text-[var(--text-muted)]" />}
        provider={genProvider} model={genModel} apiKey={genApiKey}
        providerDefaults={providerDefaults}
        onProviderChange={setGenProvider} onModelChange={setGenModel} onApiKeyChange={setGenApiKey}
      />

      <LLMSection
        title="Graph Building / Ingestion"
        icon={<Database size={15} className="text-[var(--text-muted)]" />}
        provider={ingProvider} model={ingModel} apiKey={ingApiKey}
        providerDefaults={providerDefaults}
        onProviderChange={setIngProvider} onModelChange={setIngModel} onApiKeyChange={setIngApiKey}
      />

      <div className="flex items-center gap-3 pt-1">
        <Button
          onClick={handleSave}
          loading={saving}
          icon={<Save size={14} />}
        >
          {saving ? 'Saving…' : 'Save Configuration'}
        </Button>
        {saved && (
          <span className="flex items-center gap-1.5 text-[13px] text-[var(--success)] animate-fade-in">
            <CheckCircle2 size={14} /> Saved
          </span>
        )}
      </div>

      {/* Per-task model overrides — admin defaults apply unless this founder overrides a row */}
      <div className="pt-4 border-t border-[var(--border-1)]">
        <div className="mb-3">
          <div className="text-[14px] font-semibold text-[var(--text-primary)]">Per-task model overrides</div>
          <p className="mt-1 text-[12px] text-[var(--text-muted)]">
            Admin defaults are applied for every pipeline task unless overridden below.
            Click <em>Reset</em> on any row to revert to the admin default.
          </p>
        </div>
        {slug ? (
          <div className="max-w-none -mx-2">
            <ModelsConfigPanel mode="founder" founderSlug={slug} />
          </div>
        ) : (
          <div className="text-[12px] text-[var(--text-muted)]">
            (founder slug not detected; per-task overrides are only available on a founder portal)
          </div>
        )}
      </div>
    </div>
  )
}
