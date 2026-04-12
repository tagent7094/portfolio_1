import { useEffect, useState } from 'react'
import { Save, Loader2, Cpu, Database } from 'lucide-react'
import { apiGet, apiPost } from '../api/client'
import type { LLMConfig } from '../types/api'

const PROVIDERS = ['anthropic', 'openai', 'gemini', 'nvidia', 'openrouter', 'lmstudio', 'ollama'] as const

interface ProviderDefaults {
  base_url: string
  default_model: string
  models: string[]
  has_api_key: boolean
}

interface LLMSectionProps {
  title: string
  icon: React.ReactNode
  provider: string
  model: string
  apiKey: string
  providerDefaults: Record<string, ProviderDefaults>
  onProviderChange: (p: string) => void
  onModelChange: (m: string) => void
  onApiKeyChange: (k: string) => void
}

function LLMSection({
  title, icon, provider, model, apiKey,
  providerDefaults, onProviderChange, onModelChange, onApiKeyChange,
}: LLMSectionProps) {
  const defaults = providerDefaults[provider]
  const models = defaults?.models || []
  const isLocal = provider === 'lmstudio' || provider === 'ollama'

  return (
    <div className="space-y-4 rounded-xl border border-gray-800 bg-gray-900 p-6">
      <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
        {icon}
        {title}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {/* Provider */}
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400">Provider</label>
          <select
            value={provider}
            onChange={(e) => {
              const p = e.target.value
              onProviderChange(p)
              const d = providerDefaults[p]
              if (d) onModelChange(d.default_model)
            }}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-white/30 focus:outline-none"
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>

        {/* Model */}
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400">Model</label>
          {models.length > 0 ? (
            <div className="flex gap-2">
              <select
                value={models.includes(model) ? model : ''}
                onChange={(e) => onModelChange(e.target.value)}
                className="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-white/30 focus:outline-none"
              >
                {models.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
                {!models.includes(model) && model && (
                  <option value={model}>{model} (custom)</option>
                )}
              </select>
              <input
                type="text"
                value={model}
                onChange={(e) => onModelChange(e.target.value)}
                placeholder="or type custom"
                className="w-40 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs text-gray-400 focus:border-white/30 focus:outline-none"
              />
            </div>
          ) : (
            <input
              type="text"
              value={model}
              onChange={(e) => onModelChange(e.target.value)}
              placeholder={isLocal ? 'e.g. ibm/granite-4-h-tiny' : 'Model name'}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 focus:border-white/30 focus:outline-none"
            />
          )}
        </div>
      </div>

      {/* API Key (only for cloud providers) */}
      {!isLocal && (
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400">
            API Key
            {defaults?.has_api_key && (
              <span className="ml-2 text-white/80 text-[10px]">loaded from .env</span>
            )}
          </label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => onApiKeyChange(e.target.value)}
            placeholder={defaults?.has_api_key ? '••• loaded from .env •••' : 'Paste API key'}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder:text-gray-600 focus:border-white/30 focus:outline-none"
          />
        </div>
      )}

      {/* Base URL info */}
      <div className="flex items-center gap-2 text-[11px] text-gray-500">
        <span>Base URL:</span>
        <code className="rounded bg-gray-800 px-1.5 py-0.5 text-gray-400">
          {defaults?.base_url || 'default'}
        </code>
      </div>
    </div>
  )
}

export default function ConfigPage() {
  // Generation LLM
  const [genProvider, setGenProvider] = useState('anthropic')
  const [genModel, setGenModel] = useState('')
  const [genApiKey, setGenApiKey] = useState('')

  // Ingestion LLM
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
      setGenProvider(cfg.llm.provider)
      setGenModel(cfg.llm.model)
      setGenApiKey(cfg.llm.api_key ?? '')

      const ing = (cfg as any).llm_ingestion
      if (ing) {
        setIngProvider(ing.provider || 'lmstudio')
        setIngModel(ing.model || '')
        setIngApiKey(ing.api_key ?? '')
      }

      setProviderDefaults(defaults)
      setLoaded(true)
    })
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      // Save generation LLM
      await apiPost('/api/config', {
        provider: genProvider,
        model: genModel,
        api_key: genApiKey || undefined,
      })
      // Save ingestion LLM
      await apiPost('/api/config/ingestion', {
        provider: ingProvider,
        model: ingModel,
        api_key: ingApiKey || undefined,
      })
      console.log('[Config] Saved both LLM configs')
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      console.error('[Config] Save failed:', e)
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={24} className="animate-spin text-gray-400" />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h2 className="text-2xl font-bold">LLM Configuration</h2>
      <p className="text-sm text-gray-400">
        Configure separate LLM providers for post generation (quality-critical) and graph building (bulk extraction).
        API keys and base URLs are pre-loaded from <code className="rounded bg-gray-800 px-1 text-gray-300">.env</code>
      </p>

      <LLMSection
        title="Post Generation LLM"
        icon={<Cpu size={16} className="text-white" />}
        provider={genProvider}
        model={genModel}
        apiKey={genApiKey}
        providerDefaults={providerDefaults}
        onProviderChange={setGenProvider}
        onModelChange={setGenModel}
        onApiKeyChange={setGenApiKey}
      />

      <LLMSection
        title="Graph Building / Ingestion LLM"
        icon={<Database size={16} className="text-white" />}
        provider={ingProvider}
        model={ingModel}
        apiKey={ingApiKey}
        providerDefaults={providerDefaults}
        onProviderChange={setIngProvider}
        onModelChange={setIngModel}
        onApiKeyChange={setIngApiKey}
      />

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-white px-5 py-2.5 text-sm font-medium text-black transition-colors hover:bg-white/90 disabled:opacity-50"
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>
        {saved && (
          <span className="text-sm text-white animate-pulse">Saved!</span>
        )}
      </div>
    </div>
  )
}
