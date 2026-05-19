import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Lock, Save, Loader2, CheckCircle2, Globe, Eye, EyeOff, Plus } from 'lucide-react'
import { apiGet, apiPut } from '../api/client'

interface SubdomainEntry {
  subdomain: string
  enabled: boolean
  has_password: boolean
  updated_at: string
  updated_by: string
}

const KNOWN_SUBDOMAINS = ['asksharath', 'askrevsure'] as const

export default function SubdomainAuthAdminPage() {
  const navigate = useNavigate()
  const [subdomains, setSubdomains] = useState<SubdomainEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [savingSlug, setSavingSlug] = useState<string | null>(null)
  const [showPassword, setShowPassword] = useState<Record<string, boolean>>({})
  const [draftPassword, setDraftPassword] = useState<Record<string, string>>({})
  const [savedSlug, setSavedSlug] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [newSlugInput, setNewSlugInput] = useState('')

  const reload = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiGet<{ subdomains: SubdomainEntry[] }>('/api/admin/subdomain-passwords')
      setSubdomains(data.subdomains || [])
    } catch (e: any) {
      setError(e?.message || 'Failed to load subdomain configs')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { reload() }, [])

  // Ensure both known subdomains are visible even if not yet stored.
  const merged: SubdomainEntry[] = (() => {
    const bySlug = Object.fromEntries(subdomains.map(s => [s.subdomain, s]))
    for (const known of KNOWN_SUBDOMAINS) {
      if (!bySlug[known]) {
        bySlug[known] = { subdomain: known, enabled: false, has_password: false, updated_at: '', updated_by: '' }
      }
    }
    return Object.values(bySlug).sort((a, b) => a.subdomain.localeCompare(b.subdomain))
  })()

  const save = async (slug: string, payload: { new_password?: string; enabled?: boolean }) => {
    setSavingSlug(slug)
    setError('')
    try {
      await apiPut(`/api/admin/subdomain-passwords/${slug}`, payload)
      setSavedSlug(slug)
      setTimeout(() => setSavedSlug(null), 2000)
      setDraftPassword(p => ({ ...p, [slug]: '' }))
      await reload()
    } catch (e: any) {
      setError(e?.message || `Failed to update ${slug}`)
    } finally {
      setSavingSlug(null)
    }
  }

  const addNewSlug = () => {
    const slug = newSlugInput.trim().toLowerCase()
    if (!slug) return
    if (subdomains.some(s => s.subdomain === slug)) {
      setError(`subdomain ${slug} already exists`)
      return
    }
    setSubdomains(prev => [
      ...prev,
      { subdomain: slug, enabled: false, has_password: false, updated_at: '', updated_by: '' },
    ])
    setNewSlugInput('')
  }

  return (
    <div className="min-h-screen bg-[var(--page-bg)] text-[var(--text-primary)]">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <button
          onClick={() => navigate('/admin')}
          className="mb-6 inline-flex items-center gap-2 text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)]"
        >
          <ArrowLeft size={14} />
          Back to admin
        </button>

        <header className="mb-8">
          <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-[var(--border-3)] bg-[var(--surface-3)] px-3 py-1 text-xs text-[var(--text-muted)]">
            <Lock size={12} />
            Per-subdomain auth
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">Subdomain password management</h1>
          <p className="mt-2 text-[var(--text-muted)]">
            Set a password for each public tenant site (asksharath.tagent.club, askrevsure.tagent.club, etc.).
            When <strong>enabled</strong> is on, visitors must enter the password before the API responds.
          </p>
        </header>

        {error && (
          <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 text-[var(--text-muted)]">
            <Loader2 size={16} className="animate-spin" />
            Loading subdomains…
          </div>
        ) : (
          <div className="space-y-4">
            {merged.map(entry => {
              const slug = entry.subdomain
              const draft = draftPassword[slug] || ''
              const isShowing = !!showPassword[slug]
              const isSaving = savingSlug === slug
              const wasSaved = savedSlug === slug
              return (
                <div
                  key={slug}
                  className="rounded-xl border border-[var(--border-3)] bg-[var(--surface-2)] p-5"
                >
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <Globe size={16} className="text-[var(--text-muted)]" />
                      <span className="font-mono text-lg">{slug}.tagent.club</span>
                      {entry.has_password ? (
                        <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300">
                          password set
                        </span>
                      ) : (
                        <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300">
                          no password
                        </span>
                      )}
                    </div>
                    <label className="flex cursor-pointer items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={entry.enabled}
                        disabled={!entry.has_password || isSaving}
                        onChange={(e) => save(slug, { enabled: e.target.checked })}
                        className="h-4 w-4"
                      />
                      <span className={entry.enabled ? 'text-emerald-300' : 'text-[var(--text-muted)]'}>
                        {entry.enabled ? 'Gate enabled' : 'Gate disabled'}
                      </span>
                    </label>
                  </div>

                  {entry.updated_at && (
                    <p className="mb-3 text-xs text-[var(--text-muted)]">
                      Last updated {entry.updated_at} by {entry.updated_by || 'admin'}
                    </p>
                  )}

                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <input
                        type={isShowing ? 'text' : 'password'}
                        value={draft}
                        onChange={(e) => setDraftPassword(p => ({ ...p, [slug]: e.target.value }))}
                        placeholder={entry.has_password ? 'Set a new password…' : 'Set initial password (min 6 chars)'}
                        className="w-full rounded-lg border border-[var(--border-3)] bg-[var(--surface-3)] px-3 py-2 pr-10 font-mono text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(p => ({ ...p, [slug]: !p[slug] }))}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                      >
                        {isShowing ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                    <button
                      onClick={() => save(slug, { new_password: draft })}
                      disabled={!draft || draft.length < 6 || isSaving}
                      className="inline-flex items-center gap-2 rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-[var(--accent-fg)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {isSaving ? <Loader2 size={14} className="animate-spin" /> : wasSaved ? <CheckCircle2 size={14} /> : <Save size={14} />}
                      {wasSaved ? 'Saved' : 'Save password'}
                    </button>
                  </div>
                </div>
              )
            })}

            <div className="mt-8 rounded-xl border border-dashed border-[var(--border-3)] bg-[var(--surface-2)]/50 p-5">
              <h3 className="mb-2 text-sm font-medium text-[var(--text-muted)]">Add a new subdomain</h3>
              <div className="flex gap-2">
                <input
                  value={newSlugInput}
                  onChange={(e) => setNewSlugInput(e.target.value)}
                  placeholder="askdeepinder"
                  className="flex-1 rounded-lg border border-[var(--border-3)] bg-[var(--surface-3)] px-3 py-2 text-sm"
                />
                <button
                  onClick={addNewSlug}
                  disabled={!newSlugInput.trim()}
                  className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-3)] px-4 py-2 text-sm disabled:opacity-50"
                >
                  <Plus size={14} />
                  Add
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
