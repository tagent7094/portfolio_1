import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield, LogOut, Loader2, KeyRound, Copy, CheckCircle2, RefreshCw, X, ExternalLink, FileSpreadsheet } from 'lucide-react'
import clsx from 'clsx'
import { apiGet, apiPost } from '../api/client'

const ALL_PAGES = ['dashboard', 'generate', 'customize', 'graph', 'coverage', 'workflow', 'history', 'config']

interface FounderProfile {
  slug: string
  display_name: string
  subdomain: string
  url: string
  has_password: boolean
  last_reset_at: string | null
  pages: string[]
  graph_path: string
}

function formatTimeAgo(iso: string | null): string {
  if (!iso) return 'never'
  const t = Date.parse(iso)
  if (isNaN(t)) return iso
  const delta = (Date.now() - t) / 1000
  if (delta < 60) return 'just now'
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`
  return `${Math.floor(delta / 86400)}d ago`
}

export default function AdminPage() {
  const navigate = useNavigate()
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [profiles, setProfiles] = useState<FounderProfile[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  // Reset-password modal state
  const [resettingSlug, setResettingSlug] = useState<string | null>(null)
  const [revealedPw, setRevealedPw] = useState<{ slug: string; password: string } | null>(null)
  const [copied, setCopied] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiGet<{ founders: FounderProfile[] }>('/api/admin/founders')
      setProfiles(data.founders)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  // Check admin auth, then load profiles
  useEffect(() => {
    apiGet('/api/admin/me')
      .then(() => {
        setAuthed(true)
        refresh()
      })
      .catch(() => {
        setAuthed(false)
        navigate('/admin/login', { replace: true })
      })
  }, [navigate, refresh])

  // Poll profiles every 10s for "real-time" updates (post-reset timestamps, new founders)
  useEffect(() => {
    if (!authed) return
    const id = setInterval(refresh, 10000)
    return () => clearInterval(id)
  }, [authed, refresh])

  const togglePage = async (slug: string, page: string) => {
    const profile = profiles.find((p) => p.slug === slug)
    if (!profile) return
    const current = profile.pages
    const updated = current.includes(page) ? current.filter((p) => p !== page) : [...current, page]

    setSaving(slug)
    try {
      await apiPost('/api/admin/permissions', { slug, pages: updated })
      setProfiles((prev) => prev.map((p) => (p.slug === slug ? { ...p, pages: updated } : p)))
      setSaved(slug)
      setTimeout(() => setSaved(null), 1000)
    } catch {
      // revert on error
    } finally {
      setSaving(null)
    }
  }

  const handleResetPassword = async (slug: string) => {
    setResettingSlug(slug)
    try {
      const res = await apiPost<{ password: string; last_reset_at: string }>(
        `/api/admin/founders/${slug}/reset-password`, {},
      )
      setRevealedPw({ slug, password: res.password })
      // Update the local profile with new timestamp
      setProfiles((prev) =>
        prev.map((p) =>
          p.slug === slug ? { ...p, has_password: true, last_reset_at: res.last_reset_at } : p,
        ),
      )
    } catch (e: any) {
      alert(`Failed to reset password: ${e?.message || 'unknown error'}`)
    } finally {
      setResettingSlug(null)
    }
  }

  const copyPassword = async () => {
    if (!revealedPw) return
    try {
      await navigator.clipboard.writeText(revealedPw.password)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard API unavailable — user can copy manually from the displayed text
    }
  }

  const handleLogout = async () => {
    await apiPost('/api/admin/logout', {})
    navigate('/admin/login', { replace: true })
  }

  if (authed === null) {
    return (
      <div className="flex h-screen items-center justify-center bg-black">
        <Loader2 size={20} className="animate-spin text-white" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-black text-white p-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white">
            <Shield size={20} className="text-black" />
          </div>
          <div>
            <h1 className="font-[var(--font-display)] text-xl font-semibold">Admin Panel</h1>
            <p className="text-xs text-white/50">
              {profiles.length} founder{profiles.length !== 1 ? 's' : ''} · Auto-refreshes every 10s
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/80 hover:bg-white/10 disabled:opacity-50"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/80 hover:bg-white/10"
          >
            <LogOut size={13} /> Sign out
          </button>
        </div>
      </div>

      {/* Founder profile + permissions table */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.02] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10">
                <th className="px-4 py-3 text-left text-xs font-semibold text-white/50 uppercase tracking-wider">
                  Founder
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-white/50 uppercase tracking-wider">
                  URL
                </th>
                <th className="px-4 py-3 text-center text-xs font-semibold text-white/50 uppercase tracking-wider">
                  Password
                </th>
                {ALL_PAGES.map((page) => (
                  <th
                    key={page}
                    className="px-3 py-3 text-center text-xs font-semibold text-white/50 uppercase tracking-wider whitespace-nowrap"
                  >
                    {page}
                  </th>
                ))}
                <th className="px-3 py-3 text-center text-xs font-semibold text-white/50 uppercase tracking-wider">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((profile) => {
                const { slug, display_name, url, subdomain, has_password, last_reset_at, pages } = profile
                return (
                  <tr key={slug} className="border-b border-white/5 hover:bg-white/[0.02]">
                    <td className="px-4 py-3">
                      <div className="font-medium text-white">{display_name}</div>
                      <div className="text-[10px] text-white/40 font-mono">{slug}</div>
                      <button
                        onClick={() => navigate(`/admin/founders/${slug}`)}
                        className="mt-1 inline-flex items-center gap-1 text-[10px] text-white/30 hover:text-white/70 transition-colors"
                      >
                        <FileSpreadsheet size={10} /> Post packs
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-white/50 hover:text-white underline"
                      >
                        {subdomain}.tagent.club
                        <ExternalLink size={10} />
                      </a>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => handleResetPassword(slug)}
                        disabled={resettingSlug === slug}
                        className={clsx(
                          'inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] transition-colors',
                          has_password
                            ? 'bg-white/[0.04] text-white/80 hover:bg-white/10'
                            : 'bg-white text-black hover:bg-white/90',
                        )}
                        title={has_password ? 'Reset password' : 'Set password'}
                      >
                        {resettingSlug === slug ? (
                          <Loader2 size={11} className="animate-spin" />
                        ) : (
                          <KeyRound size={11} />
                        )}
                        {has_password ? 'Reset' : 'Set'}
                      </button>
                      {last_reset_at && (
                        <div className="mt-1 text-[10px] text-white/30">
                          {formatTimeAgo(last_reset_at)}
                        </div>
                      )}
                    </td>
                    {ALL_PAGES.map((page) => (
                      <td key={page} className="px-3 py-3 text-center">
                        <button
                          onClick={() => togglePage(slug, page)}
                          disabled={saving === slug}
                          className={clsx(
                            'h-6 w-6 rounded border transition-all',
                            pages.includes(page)
                              ? 'bg-white border-white text-black'
                              : 'bg-transparent border-white/20 text-transparent hover:border-white/40',
                          )}
                        >
                          {pages.includes(page) && (
                            <svg className="mx-auto h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                              <path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z" />
                            </svg>
                          )}
                        </button>
                      </td>
                    ))}
                    <td className="px-3 py-3 text-center">
                      {saving === slug ? (
                        <Loader2 size={14} className="mx-auto animate-spin text-white/50" />
                      ) : saved === slug ? (
                        <span className="text-xs text-white">Saved</span>
                      ) : (
                        <span className="text-xs text-white/30">
                          {pages.length} page{pages.length !== 1 ? 's' : ''}
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {profiles.length === 0 && !loading && (
        <div className="mt-8 text-center text-sm text-white/50">
          No founders configured. Push a founder folder to <code className="rounded bg-white/10 px-1.5 py-0.5 text-xs">data/founders/&lt;slug&gt;/founder-data/</code> and the next deploy will auto-provision them.
        </div>
      )}

      {/* Reveal-password modal */}
      {revealedPw && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-white/20 bg-black p-6 shadow-2xl">
            <div className="mb-4 flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold text-white">
                  <KeyRound size={14} /> New password for {revealedPw.slug}
                </div>
                <p className="mt-1 text-[11px] text-white/60">
                  Copy it now — <span className="text-white">it will never be shown again</span>.
                </p>
              </div>
              <button
                onClick={() => {
                  setRevealedPw(null)
                  setCopied(false)
                }}
                className="text-white/50 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <div className="mb-4 flex items-center gap-2 rounded-lg border border-white/20 bg-white/[0.04] p-3">
              <code className="flex-1 font-mono text-sm text-white break-all">
                {revealedPw.password}
              </code>
              <button
                onClick={copyPassword}
                className="flex items-center gap-1 rounded bg-white px-3 py-1.5 text-xs font-semibold text-black hover:bg-white/90"
              >
                {copied ? <CheckCircle2 size={13} /> : <Copy size={13} />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>

            <button
              onClick={() => {
                setRevealedPw(null)
                setCopied(false)
              }}
              className="w-full rounded-lg border border-white/20 px-3 py-2 text-sm text-white hover:bg-white/5"
            >
              I've saved it
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
