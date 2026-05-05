import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Save, Loader2, CheckCircle2, FileText, MessageCircle, Sparkles } from 'lucide-react'
import { apiGet, apiPut } from '../api/client'

interface ChatConfig {
  system_prompt: string
  post_writing_instructions: string
  opening_line_amplifier: string
}

const SECTIONS = [
  {
    key: 'system_prompt' as const,
    label: 'Chatbot System Prompt',
    icon: MessageCircle,
    description: 'Instructions that define how the AskSharath chatbot responds to questions.',
  },
  {
    key: 'post_writing_instructions' as const,
    label: 'Post Writing Instructions',
    icon: FileText,
    description: 'Ghostwriting system instructions for LinkedIn post generation.',
  },
  {
    key: 'opening_line_amplifier' as const,
    label: 'Opening Line Amplifier',
    icon: Sparkles,
    description: 'Instructions for generating powerful opening hooks.',
  },
]

export default function AskSharathAdminPage() {
  const navigate = useNavigate()
  const [config, setConfig] = useState<ChatConfig>({
    system_prompt: '',
    post_writing_instructions: '',
    opening_line_amplifier: '',
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    apiGet<ChatConfig>('/api/admin/chat-config')
      .then(setConfig)
      .catch((e) => {
        if (String(e).includes('401')) navigate('/admin/login', { replace: true })
      })
      .finally(() => setLoading(false))
  }, [navigate])

  const handleSave = async () => {
    setSaving(true)
    try {
      await apiPut('/api/admin/chat-config', config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e: any) {
      alert(`Save failed: ${e?.message}`)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--page-bg)]">
        <Loader2 size={24} className="animate-spin text-[var(--text-muted)]" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[var(--page-bg)] px-4 py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mx-auto max-w-3xl">
        <div className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/admin')}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]"
            >
              <ArrowLeft size={16} />
            </button>
            <div>
              <h1 className="font-[var(--font-display)] text-[18px] font-semibold text-[var(--text-primary)]">
                AskSharath Config
              </h1>
              <p className="text-[12px] text-[var(--text-muted)]">
                Edit chatbot and generation instructions
              </p>
            </div>
          </div>
          <button
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-[13px] font-medium text-black transition-all hover:scale-105 active:scale-95 disabled:opacity-50"
          >
            {saving ? (
              <Loader2 size={14} className="animate-spin" />
            ) : saved ? (
              <CheckCircle2 size={14} />
            ) : (
              <Save size={14} />
            )}
            {saving ? 'Saving…' : saved ? 'Saved' : 'Save all'}
          </button>
        </div>

        {/* Instruction sections */}
        <div className="space-y-6">
          {SECTIONS.map(({ key, label, icon: Icon, description }) => (
            <div
              key={key}
              className="rounded-xl border border-[var(--border-1)] bg-[var(--surface-2)]"
            >
              <div className="flex items-center gap-2.5 border-b border-[var(--border-2)] px-5 py-3.5">
                <Icon size={15} className="text-[var(--text-muted)]" />
                <div>
                  <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">{label}</h2>
                  <p className="text-[11px] text-[var(--text-muted)]">{description}</p>
                </div>
              </div>
              <div className="p-4">
                <textarea
                  value={config[key]}
                  onChange={(e) => setConfig((prev) => ({ ...prev, [key]: e.target.value }))}
                  className="field min-h-[200px] resize-y font-[var(--font-mono)] text-[12.5px] leading-[1.7]"
                  placeholder={`Paste ${label.toLowerCase()} content here…`}
                />
                <p className="mt-2 text-right text-[10px] text-[var(--text-muted)]">
                  {config[key].length.toLocaleString()} characters
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
