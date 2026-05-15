import { useEffect, useMemo, useState } from 'react'
import { Save, RotateCcw, Beaker, CheckCircle2, XCircle, AlertTriangle, ChevronDown, ChevronRight, KeyRound } from 'lucide-react'
import { apiGet, apiPut, apiPost, apiDelete } from '../../api/client'
import { Card, CardHeader, CardBody, CardTitle, Button, Spinner } from '../ui'

interface ModelEntry { id: string; label: string; tier: string }
interface ProviderEntry {
  label: string
  models: ModelEntry[]
  supports: string[]
  base_url: string
  api_key_env: string
  custom_models_allowed: boolean
  key_present: boolean
  key_source: string
}
interface TaskSpec {
  task_id: string
  display_name: string
  description: string
  call_site: string
  default_purpose: string
  quality_tier: 'heavy' | 'medium' | 'light'
  frequency: string
  default_temperature: number
  default_max_tokens: number
}
interface TaskConfig {
  provider: string
  model: string
  max_tokens?: number
  temperature?: number
  enable_thinking?: boolean
  effort?: string
  _source?: 'founder' | 'admin' | 'default'
}
interface AdminConfig {
  version: number
  updated_at: string
  tasks: Record<string, TaskConfig>
  provider_keys?: Record<string, string>
}
interface FounderConfig {
  admin_defaults: AdminConfig
  founder_overrides: { tasks: Record<string, TaskConfig> }
  resolved: Record<string, TaskConfig & { _source: 'founder' | 'admin' | 'default' }>
  provider_keys?: Record<string, string>
}
interface TestResult { ok: boolean; latency_ms: number; sample_output: string; error?: string }

type Mode = 'admin' | 'founder'

interface Props {
  mode: Mode
  founderSlug?: string
}

const TIER_ORDER: TaskSpec['quality_tier'][] = ['heavy', 'medium', 'light']
const TIER_LABEL: Record<TaskSpec['quality_tier'], string> = { heavy: 'Heavy (creative)', medium: 'Medium (analysis)', light: 'Light (utility)' }
const SOURCE_BADGE_COLOR: Record<string, string> = { founder: 'bg-purple-500/20 text-purple-300 border-purple-500/30', admin: 'bg-blue-500/20 text-blue-300 border-blue-500/30', default: 'bg-white/10 text-white/50 border-white/10' }

export default function ModelsConfigPanel({ mode, founderSlug }: Props) {
  const [providers, setProviders] = useState<Record<string, ProviderEntry>>({})
  const [tasks, setTasks] = useState<TaskSpec[]>([])
  const [configByTask, setConfigByTask] = useState<Record<string, TaskConfig>>({})
  const [sources, setSources] = useState<Record<string, 'founder' | 'admin' | 'default'>>({})
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({ light: true, keys: true })
  const [providerKeys, setProviderKeys] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [savingKeys, setSavingKeys] = useState(false)
  const [savedKeys, setSavedKeys] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})
  const [testing, setTesting] = useState<Record<string, boolean>>({})

  const isFounder = mode === 'founder'

  useEffect(() => { refresh() }, [mode, founderSlug])

  const refresh = async () => {
    setLoading(true)
    setError(null)
    setProviderKeys({})
    try {
      const [pData, tData] = await Promise.all([
        apiGet<{ providers: Record<string, ProviderEntry> }>('/api/admin/models/providers'),
        apiGet<{ tasks: TaskSpec[] }>('/api/admin/models/tasks'),
      ])
      setProviders(pData.providers)
      setTasks(tData.tasks)

      if (isFounder && founderSlug) {
        const merged = await apiGet<FounderConfig>(`/api/founders/${founderSlug}/models/config`)
        const cfg: Record<string, TaskConfig> = {}
        const src: Record<string, 'founder' | 'admin' | 'default'> = {}
        for (const [tid, entry] of Object.entries(merged.resolved)) {
          cfg[tid] = { ...entry }
          src[tid] = entry._source
        }
        setConfigByTask(cfg)
        setSources(src)
      } else {
        const adminCfg = await apiGet<AdminConfig>('/api/admin/models/config')
        const cfg: Record<string, TaskConfig> = {}
        for (const t of tData.tasks) {
          cfg[t.task_id] = adminCfg.tasks?.[t.task_id] ?? {
            provider: 'anthropic',
            model: 'claude-opus-4-6',
            max_tokens: t.default_max_tokens,
            temperature: t.default_temperature,
          }
        }
        setConfigByTask(cfg)
        setSources({})
      }
    } catch (e: any) {
      setError(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }

  const updateTask = (taskId: string, patch: Partial<TaskConfig>) => {
    setConfigByTask((prev) => {
      const cur = prev[taskId] || {} as TaskConfig
      const next = { ...cur, ...patch }
      // If the provider changed, snap to that provider's default model.
      if (patch.provider && providers[patch.provider]) {
        const models = providers[patch.provider].models
        if (!models.some((m) => m.id === next.model)) {
          next.model = models[0]?.id || ''
        }
      }
      return { ...prev, [taskId]: next }
    })
    if (isFounder) {
      // Marking the row as a founder override; final source comes back from server on save.
      setSources((prev) => ({ ...prev, [taskId]: 'founder' }))
    }
  }

  const resetTaskToAdmin = async (taskId: string) => {
    if (!isFounder || !founderSlug) return
    try {
      await apiDelete(`/api/founders/${founderSlug}/models/config/${taskId}`)
      refresh()
    } catch (e: any) {
      setError(String(e?.message || e))
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      if (isFounder && founderSlug) {
        // Only send tasks whose source is "founder" — those are the active overrides.
        const overrides: Record<string, TaskConfig> = {}
        for (const [tid, cfg] of Object.entries(configByTask)) {
          if (sources[tid] === 'founder') {
            overrides[tid] = stripSource(cfg)
          }
        }
        const keysToSend = Object.fromEntries(Object.entries(providerKeys).filter(([, v]) => v))
        await apiPut(`/api/founders/${founderSlug}/models/config`, { tasks: overrides, provider_keys: keysToSend })
      } else {
        const body: Record<string, TaskConfig> = {}
        for (const [tid, cfg] of Object.entries(configByTask)) body[tid] = stripSource(cfg)
        const keysToSend = Object.fromEntries(Object.entries(providerKeys).filter(([, v]) => v))
        await apiPut('/api/admin/models/config', { tasks: body, provider_keys: keysToSend })
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      refresh()
    } catch (e: any) {
      setError(String(e?.message || e))
    } finally {
      setSaving(false)
    }
  }

  const handleSaveKeys = async () => {
    const keysToSend = Object.fromEntries(Object.entries(providerKeys).filter(([, v]) => v))
    if (!Object.keys(keysToSend).length) return
    setSavingKeys(true)
    setSavedKeys(false)
    setError(null)
    try {
      const endpoint = isFounder && founderSlug
        ? `/api/founders/${founderSlug}/models/keys`
        : '/api/admin/models/keys'
      await apiPut(endpoint, { provider_keys: keysToSend })
      setSavedKeys(true)
      setProviderKeys({})
      setTimeout(() => setSavedKeys(false), 3000)
      refresh()
    } catch (e: any) {
      setError(String(e?.message || e))
    } finally {
      setSavingKeys(false)
    }
  }

  const handleTest = async (taskId: string) => {
    const cfg = configByTask[taskId]
    if (!cfg) return
    setTesting((p) => ({ ...p, [taskId]: true }))
    try {
      const endpoint = isFounder && founderSlug
        ? `/api/founders/${founderSlug}/models/test`
        : '/api/admin/models/test'
      const result = await apiPost<TestResult>(endpoint, {
        provider: cfg.provider, model: cfg.model,
      })
      setTestResults((p) => ({ ...p, [taskId]: result }))
    } catch (e: any) {
      setTestResults((p) => ({ ...p, [taskId]: { ok: false, latency_ms: 0, sample_output: '', error: String(e?.message || e) } }))
    } finally {
      setTesting((p) => ({ ...p, [taskId]: false }))
    }
  }

  const [bulkProvider, setBulkProvider] = useState('')
  const [bulkModel, setBulkModel] = useState('')
  const [bulkTier, setBulkTier] = useState<'all' | 'heavy' | 'medium' | 'light'>('all')

  const bulkModels = bulkProvider ? (providers[bulkProvider]?.models || []) : []

  const applyBulk = () => {
    if (!bulkProvider || !bulkModel) return
    const affected = tasks.filter((t) => bulkTier === 'all' || t.quality_tier === bulkTier)
    setConfigByTask((prev) => {
      const next = { ...prev }
      for (const t of affected) {
        next[t.task_id] = { ...next[t.task_id], provider: bulkProvider, model: bulkModel }
      }
      return next
    })
    if (isFounder) {
      setSources((prev) => {
        const next = { ...prev }
        for (const t of affected) next[t.task_id] = 'founder'
        return next
      })
    }
  }

  const tasksByTier = useMemo(() => {
    const grouped: Record<TaskSpec['quality_tier'], TaskSpec[]> = { heavy: [], medium: [], light: [] }
    for (const t of tasks) grouped[t.quality_tier].push(t)
    return grouped
  }, [tasks])

  if (loading) return <Spinner fullPage />

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          {error}
        </div>
      )}

      {/* Quick-switch: apply one provider+model to all (or a tier of) tasks */}
      <Card>
        <CardBody className="flex items-end gap-3 flex-wrap">
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-white/40">Switch all to</label>
            <select value={bulkProvider}
              onChange={(e) => {
                setBulkProvider(e.target.value)
                const first = providers[e.target.value]?.models?.[0]?.id || ''
                setBulkModel(first)
              }}
              className="bg-white/5 text-white/80 rounded px-2 py-1.5 text-xs border border-white/10 [&>option]:bg-[#1a1a1f] [&>option]:text-white/90 w-40">
              <option value="">Provider…</option>
              {Object.entries(providers).map(([name, info]) => (
                <option key={name} value={name}>{info.label || name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-white/40">Model</label>
            <select value={bulkModel}
              onChange={(e) => setBulkModel(e.target.value)}
              className="bg-white/5 text-white/80 rounded px-2 py-1.5 text-xs border border-white/10 [&>option]:bg-[#1a1a1f] [&>option]:text-white/90 w-56"
              disabled={!bulkProvider}>
              {bulkModels.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
              {bulkModel && !bulkModels.some((m) => m.id === bulkModel) && (
                <option value={bulkModel}>{bulkModel} (custom)</option>
              )}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-white/40">Apply to</label>
            <select value={bulkTier}
              onChange={(e) => setBulkTier(e.target.value as any)}
              className="bg-white/5 text-white/80 rounded px-2 py-1.5 text-xs border border-white/10 [&>option]:bg-[#1a1a1f] [&>option]:text-white/90 w-32">
              <option value="all">All tasks</option>
              <option value="heavy">Heavy only</option>
              <option value="medium">Medium only</option>
              <option value="light">Light only</option>
            </select>
          </div>
          <Button onClick={applyBulk} disabled={!bulkProvider || !bulkModel}
            className="text-xs">
            Apply
          </Button>
        </CardBody>
      </Card>

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          {Object.entries(providers).map(([name, info]) => (
            <span key={name}
              className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${
                info.key_present
                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                  : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
              }`}
              title={info.api_key_env ? `env: ${info.api_key_env}` : 'local provider, no key needed'}
            >
              {info.key_present ? <CheckCircle2 size={11} /> : <AlertTriangle size={11} />}
              {info.label || name}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {saved && <span className="flex items-center gap-1 text-[12px] text-emerald-400"><CheckCircle2 size={13} /> Saved</span>}
          <Button onClick={handleSave} loading={saving} icon={<Save size={14} />}>
            {saving ? 'Saving…' : (isFounder ? 'Save overrides' : 'Save admin defaults')}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between w-full">
            <button
              onClick={() => setCollapsed((p) => ({ ...p, keys: !p.keys }))}
              className="flex items-center gap-1.5 text-left"
            >
              {collapsed.keys ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
              <CardTitle><span className="flex items-center gap-1.5"><KeyRound size={14} /> API Keys</span></CardTitle>
            </button>
            {!collapsed.keys && (
              <div className="flex items-center gap-2">
                {savedKeys && <span className="flex items-center gap-1 text-[11px] text-emerald-400"><CheckCircle2 size={11} /> Saved</span>}
                <Button onClick={handleSaveKeys} loading={savingKeys} icon={<Save size={12} />}
                  className="text-[11px] px-2 py-1">
                  {savingKeys ? 'Saving…' : 'Save Keys'}
                </Button>
              </div>
            )}
          </div>
        </CardHeader>
        {!collapsed.keys && (
          <CardBody className="space-y-3">
            <p className="text-[11px] text-white/40">
              Enter API keys here or set them as environment variables on the server.
              {isFounder && ' Keys you set here override the admin defaults for your pipeline runs.'}
            </p>
            {Object.entries(providers)
              .filter(([name]) => name !== 'ollama' && name !== 'lmstudio')
              .map(([name, info]) => (
                <div key={name} className="flex items-center gap-3">
                  <div className="w-44 text-[12px] text-white/70 flex items-center gap-1.5 shrink-0">
                    <span className={`inline-block w-1.5 h-1.5 rounded-full ${
                      info.key_present ? 'bg-emerald-400' : 'bg-white/20'
                    }`} />
                    {info.label || name}
                  </div>
                  <input
                    type="password"
                    value={providerKeys[name] || ''}
                    onChange={(e) => setProviderKeys((p) => ({ ...p, [name]: e.target.value }))}
                    placeholder={
                      info.key_source === 'env' ? `Loaded from ${info.api_key_env}`
                        : info.key_source === 'saved' ? 'Key saved — enter new value to replace'
                        : 'Enter API key…'
                    }
                    className="flex-1 bg-white/5 text-white/80 rounded px-2 py-1.5 text-xs border border-white/10 font-mono placeholder:text-white/25"
                  />
                  {info.key_source !== 'none' && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full border shrink-0 ${
                      info.key_source === 'env' ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                        : info.key_source === 'saved' ? 'border-blue-500/30 bg-blue-500/10 text-blue-300'
                        : 'border-white/10 text-white/30'
                    }`}>{info.key_source}</span>
                  )}
                </div>
              ))
            }
          </CardBody>
        )}
      </Card>

      {TIER_ORDER.map((tier) => {
        const tierTasks = tasksByTier[tier]
        if (!tierTasks.length) return null
        const isCollapsed = collapsed[tier] === true
        return (
          <Card key={tier}>
            <CardHeader>
              <button
                onClick={() => setCollapsed((p) => ({ ...p, [tier]: !p[tier] }))}
                className="flex items-center gap-1.5 text-left"
              >
                {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                <CardTitle>{TIER_LABEL[tier]} <span className="text-white/40 font-normal">({tierTasks.length})</span></CardTitle>
              </button>
            </CardHeader>
            {!isCollapsed && (
              <CardBody className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-white/[0.02] text-white/40">
                      <tr>
                        <th className="text-left px-3 py-2 font-medium">Task</th>
                        <th className="text-left px-2 py-2 font-medium w-44">Provider</th>
                        <th className="text-left px-2 py-2 font-medium w-64">Model</th>
                        <th className="text-right px-2 py-2 font-medium w-20">Max tokens</th>
                        <th className="text-right px-2 py-2 font-medium w-16">Temp</th>
                        {isFounder && <th className="text-left px-2 py-2 font-medium w-20">Source</th>}
                        <th className="text-left px-2 py-2 font-medium w-40">Test</th>
                        {isFounder && <th className="w-10"></th>}
                      </tr>
                    </thead>
                    <tbody>
                      {tierTasks.map((t) => {
                        const cfg = configByTask[t.task_id] || { provider: 'anthropic', model: '' }
                        const providerInfo = providers[cfg.provider]
                        const models = providerInfo?.models || []
                        const source = sources[t.task_id] || 'default'
                        const result = testResults[t.task_id]
                        const isModelCustom = !models.some((m) => m.id === cfg.model)
                        return (
                          <tr key={t.task_id} className="border-t border-white/[0.04] hover:bg-white/[0.02]">
                            <td className="px-3 py-2">
                              <div className="font-medium text-white/80" title={t.description}>{t.display_name}</div>
                              <div className="text-[10px] text-white/30">{t.frequency} · {t.call_site.split('/').pop()}</div>
                            </td>
                            <td className="px-2 py-2">
                              <select value={cfg.provider}
                                onChange={(e) => updateTask(t.task_id, { provider: e.target.value })}
                                className="w-full bg-white/5 text-white/80 rounded px-1.5 py-1 text-xs border border-white/10 [&>option]:bg-[#1a1a1f] [&>option]:text-white/90">
                                {Object.entries(providers).map(([name, info]) => (
                                  <option key={name} value={name}>{info.label || name}</option>
                                ))}
                              </select>
                            </td>
                            <td className="px-2 py-2">
                              <div className="flex gap-1">
                                <select value={isModelCustom ? '__custom__' : cfg.model}
                                  onChange={(e) => {
                                    if (e.target.value === '__custom__') return
                                    updateTask(t.task_id, { model: e.target.value })
                                  }}
                                  className="flex-1 bg-white/5 text-white/80 rounded px-1.5 py-1 text-xs border border-white/10 [&>option]:bg-[#1a1a1f] [&>option]:text-white/90">
                                  {models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                                  <option value="__custom__">Custom…</option>
                                </select>
                                {isModelCustom && (
                                  <input type="text" value={cfg.model}
                                    onChange={(e) => updateTask(t.task_id, { model: e.target.value })}
                                    placeholder="model id"
                                    className="w-32 bg-white/5 text-white/80 rounded px-1.5 py-1 text-xs border border-white/10 font-mono" />
                                )}
                              </div>
                            </td>
                            <td className="px-2 py-2">
                              <input type="number" value={cfg.max_tokens ?? t.default_max_tokens}
                                onChange={(e) => updateTask(t.task_id, { max_tokens: Number(e.target.value) })}
                                className="w-full bg-white/5 text-white/80 rounded px-1.5 py-1 text-xs border border-white/10 text-right" />
                            </td>
                            <td className="px-2 py-2">
                              <input type="number" step="0.1" min="0" max="1" value={cfg.temperature ?? t.default_temperature}
                                onChange={(e) => updateTask(t.task_id, { temperature: Number(e.target.value) })}
                                className="w-full bg-white/5 text-white/80 rounded px-1.5 py-1 text-xs border border-white/10 text-right" />
                            </td>
                            {isFounder && (
                              <td className="px-2 py-2">
                                <span className={`inline-flex rounded-full border px-1.5 py-0.5 text-[10px] ${SOURCE_BADGE_COLOR[source] || SOURCE_BADGE_COLOR.default}`}>
                                  {source}
                                </span>
                              </td>
                            )}
                            <td className="px-2 py-2">
                              <div className="flex items-center gap-1.5">
                                <button onClick={() => handleTest(t.task_id)} disabled={testing[t.task_id]}
                                  className="flex items-center gap-1 rounded bg-white/5 hover:bg-white/10 px-1.5 py-1 text-[11px] text-white/60 border border-white/10">
                                  <Beaker size={11} /> {testing[t.task_id] ? '…' : 'Test'}
                                </button>
                                {result && (
                                  result.ok
                                    ? <span className="flex items-center gap-1 text-[10px] text-emerald-400" title={result.sample_output}>
                                        <CheckCircle2 size={11} /> {result.latency_ms}ms
                                      </span>
                                    : <span className="flex items-center gap-1 text-[10px] text-red-400" title={result.error}>
                                        <XCircle size={11} /> fail
                                      </span>
                                )}
                              </div>
                            </td>
                            {isFounder && (
                              <td className="px-2 py-2">
                                {source === 'founder' && (
                                  <button onClick={() => resetTaskToAdmin(t.task_id)}
                                    title="Reset to admin default"
                                    className="text-white/40 hover:text-white/70">
                                    <RotateCcw size={12} />
                                  </button>
                                )}
                              </td>
                            )}
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </CardBody>
            )}
          </Card>
        )
      })}
    </div>
  )
}

function stripSource(cfg: TaskConfig): TaskConfig {
  const { _source: _drop, ...rest } = cfg as any
  return rest
}
