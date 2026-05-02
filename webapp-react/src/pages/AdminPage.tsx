import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Shield, LogOut, Loader2, KeyRound, Copy, CheckCircle2,
  RefreshCw, X, ExternalLink, FileSpreadsheet,
} from 'lucide-react'
import clsx from 'clsx'
import { apiGet, apiPost } from '../api/client'
import { Button, Badge, Card, CardHeader, CardBody, Spinner } from '../components/ui'

const ALL_PAGES = ['dashboard', 'generate', 'customize', 'graph', 'coverage', 'workflow', 'history', 'config']

interface FounderProfile {
  slug: string; display_name: string; subdomain: string; url: string
  has_password: boolean; last_reset_at: string | null; pages: string[]; graph_path: string
}

function formatTimeAgo(iso: string | null): string {
  if (!iso) return 'never'
  const delta = (Date.now() - Date.parse(iso)) / 1000
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
  const [resettingSlug, setResettingSlug] = useState<string | null>(null)
  const [revealedPw, setRevealedPw] = useState<{ slug: string; password: string } | null>(null)
  const [copied, setCopied] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiGet<{ founders: FounderProfile[] }>('/api/admin/founders')
      setProfiles(data.founders)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    apiGet('/api/admin/me')
      .then(() => { setAuthed(true); refresh() })
      .catch(() => { setAuthed(false); navigate('/admin/login', { replace: true }) })
  }, [navigate, refresh])

  useEffect(() => {
    if (!authed) return
    const id = setInterval(refresh, 10000)
    return () => clearInterval(id)
  }, [authed, refresh])

  const togglePage = async (slug: string, page: string) => {
    const profile = profiles.find((p) => p.slug === slug)
    if (!profile) return
    const updated = profile.pages.includes(page)
      ? profile.pages.filter((p) => p !== page)
      : [...profile.pages, page]
    setSaving(slug)
    try {
      await apiPost('/api/admin/permissions', { slug, pages: updated })
      setProfiles((prev) => prev.map((p) => p.slug === slug ? { ...p, pages: updated } : p))
      setSaved(slug); setTimeout(() => setSaved(null), 1200)
    } catch { /* revert */ }
    finally { setSaving(null) }
  }

  const handleResetPassword = async (slug: string) => {
    setResettingSlug(slug)
    try {
      const res = await apiPost<{ password: string; last_reset_at: string }>(
        `/api/admin/founders/${slug}/reset-password`, {},
      )
      setRevealedPw({ slug, password: res.password })
      setProfiles((prev) => prev.map((p) => p.slug === slug ? { ...p, has_password: true, last_reset_at: res.last_reset_at } : p))
    } catch (e: any) { alert(`Failed to reset: ${e?.message}`) }
    finally { setResettingSlug(null) }
  }

  const copyPassword = async () => {
    if (!revealedPw) return
    await navigator.clipboard.writeText(revealedPw.password).catch(() => {})
    setCopied(true); setTimeout(() => setCopied(false), 1500)
  }

  const handleLogout = async () => {
    await apiPost('/api/admin/logout', {})
    navigate('/admin/login', { replace: true })
  }

  if (authed === null) return <Spinner fullPage />

  return (
    <div className="min-h-screen bg-[var(--page-bg)] px-4 py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--surface-3)]">
            <Shield size={18} className="text-[var(--text-secondary)]" />
          </div>
          <div>
            <h1 className="font-[var(--font-display)] text-[18px] font-semibold text-[var(--text-primary)]">
              Admin Panel
            </h1>
            <p className="text-[12px] text-[var(--text-muted)]">
              {profiles.length} founder{profiles.length !== 1 ? 's' : ''} · auto-refresh 10s
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={refresh} disabled={loading} icon={<RefreshCw size={13} className={loading ? 'animate-spin' : ''} />}>
            Refresh
          </Button>
          <Button variant="ghost" size="sm" onClick={handleLogout} icon={<LogOut size={13} />}>
            Sign out
          </Button>
        </div>
      </div>

      {/* Founders table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-[var(--border-1)]">
                <th className="px-5 py-3.5 text-left text-[10.5px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Founder</th>
                <th className="px-5 py-3.5 text-left text-[10.5px] font-semibold uppercase tracking-widest text-[var(--text-muted)] hidden sm:table-cell">URL</th>
                <th className="px-5 py-3.5 text-center text-[10.5px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Password</th>
                {ALL_PAGES.map((page) => (
                  <th key={page} className="px-2.5 py-3.5 text-center text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)] whitespace-nowrap hidden md:table-cell">
                    {page}
                  </th>
                ))}
                <th className="px-3 py-3.5 text-center text-[10.5px] font-semibold uppercase tracking-widest text-[var(--text-muted)] hidden md:table-cell">Status</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((profile) => {
                const { slug, display_name, url, subdomain, has_password, last_reset_at, pages } = profile
                return (
                  <tr key={slug} className="border-b border-[var(--border-2)] transition-colors hover:bg-[var(--row-hover)] last:border-0">
                    <td className="px-5 py-3.5">
                      <p className="font-semibold text-[var(--text-primary)]">{display_name}</p>
                      <p className="mt-0.5 font-[var(--font-mono)] text-[11px] text-[var(--text-muted)]">{slug}</p>
                      <button
                        onClick={() => navigate(`/admin/founders/${slug}`)}
                        className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
                      >
                        <FileSpreadsheet size={11} /> Post packs
                      </button>
                    </td>
                    <td className="px-5 py-3.5 hidden sm:table-cell">
                      <a
                        href={url} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]"
                      >
                        {subdomain}.tagent.club <ExternalLink size={11} />
                      </a>
                    </td>
                    <td className="px-5 py-3.5 text-center">
                      <div className="flex flex-col items-center gap-1">
                        <Button
                          variant={has_password ? 'ghost' : 'primary'}
                          size="xs"
                          onClick={() => handleResetPassword(slug)}
                          disabled={resettingSlug === slug}
                          loading={resettingSlug === slug}
                          icon={<KeyRound size={11} />}
                        >
                          {has_password ? 'Reset' : 'Set'}
                        </Button>
                        {last_reset_at && (
                          <span className="text-[10px] text-[var(--text-muted)]">{formatTimeAgo(last_reset_at)}</span>
                        )}
                      </div>
                    </td>
                    {ALL_PAGES.map((page) => (
                      <td key={page} className="px-2.5 py-3.5 text-center hidden md:table-cell">
                        <button
                          onClick={() => togglePage(slug, page)}
                          disabled={saving === slug}
                          className={clsx(
                            'h-6 w-6 rounded-md border transition-all duration-100',
                            pages.includes(page)
                              ? 'bg-white border-white text-black hover:bg-white/80'
                              : 'border-[var(--border-3)] bg-transparent hover:border-[var(--text-muted)]',
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
                    <td className="px-3 py-3.5 text-center hidden md:table-cell">
                      {saving === slug ? (
                        <Loader2 size={14} className="mx-auto animate-spin text-[var(--text-muted)]" />
                      ) : saved === slug ? (
                        <CheckCircle2 size={14} className="mx-auto text-[var(--success)]" />
                      ) : (
                        <Badge variant="default">{pages.length}</Badge>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {profiles.length === 0 && !loading && (
          <CardBody>
            <p className="py-6 text-center text-[13px] text-[var(--text-muted)]">
              No founders configured yet. Push a founder folder to{' '}
              <code className="rounded-md bg-[var(--surface-3)] px-1.5 py-0.5 text-[11.5px]">
                data/founders/&lt;slug&gt;/
              </code>
            </p>
          </CardBody>
        )}
      </Card>

      {/* Reveal password modal */}
      {revealedPw && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => { setRevealedPw(null); setCopied(false) }} />
          <div className="relative w-full max-w-md animate-scale-in rounded-2xl border border-[var(--border-1)] bg-[var(--surface-2)] p-6 shadow-[var(--shadow-overlay)]">
            <div className="mb-5 flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 text-[14px] font-semibold text-[var(--text-primary)]">
                  <KeyRound size={14} /> New password for <span className="font-[var(--font-mono)]">{revealedPw.slug}</span>
                </div>
                <p className="mt-1 text-[12px] text-[var(--text-muted)]">
                  Copy it now — it will <em>not</em> be shown again.
                </p>
              </div>
              <button
                onClick={() => { setRevealedPw(null); setCopied(false) }}
                className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--text-muted)] hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)] transition-colors"
              >
                <X size={15} />
              </button>
            </div>

            <div className="mb-4 flex items-center gap-2 rounded-xl border border-[var(--border-3)] bg-[var(--surface-3)] p-3.5">
              <code className="flex-1 break-all font-[var(--font-mono)] text-[14px] text-[var(--text-primary)]">
                {revealedPw.password}
              </code>
              <Button variant="primary" size="sm" onClick={copyPassword} icon={copied ? <CheckCircle2 size={13} /> : <Copy size={13} />}>
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>

            <Button variant="secondary" className="w-full" onClick={() => { setRevealedPw(null); setCopied(false) }}>
              Done
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
