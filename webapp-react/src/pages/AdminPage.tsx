import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield, LogOut, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { apiGet, apiPost } from '../api/client'

const ALL_PAGES = ['dashboard', 'generate', 'customize', 'graph', 'coverage', 'workflow', 'history', 'config']

interface PermissionsData {
  permissions: Record<string, string[]>
  all_pages: string[]
}

export default function AdminPage() {
  const navigate = useNavigate()
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [perms, setPerms] = useState<Record<string, string[]>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)

  // Check admin auth on mount
  useEffect(() => {
    apiGet('/api/admin/me')
      .then(() => setAuthed(true))
      .catch(() => {
        setAuthed(false)
        navigate('/admin/login', { replace: true })
      })
  }, [navigate])

  // Load permissions
  useEffect(() => {
    if (!authed) return
    apiGet<PermissionsData>('/api/admin/permissions')
      .then((data) => setPerms(data.permissions))
      .catch(() => {})
  }, [authed])

  const togglePage = async (slug: string, page: string) => {
    const current = perms[slug] || []
    const updated = current.includes(page)
      ? current.filter((p) => p !== page)
      : [...current, page]

    setSaving(slug)
    try {
      await apiPost('/api/admin/permissions', { slug, pages: updated })
      setPerms((prev) => ({ ...prev, [slug]: updated }))
      setSaved(slug)
      setTimeout(() => setSaved(null), 1000)
    } catch {
      // revert on error
    } finally {
      setSaving(null)
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

  const founders = Object.keys(perms).sort()

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
            <p className="text-xs text-white/50">Manage founder page visibility</p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/80 hover:bg-white/10"
        >
          <LogOut size={13} /> Sign out
        </button>
      </div>

      {/* Permissions Matrix */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.02] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10">
                <th className="px-4 py-3 text-left text-xs font-semibold text-white/50 uppercase tracking-wider">Founder</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-white/50 uppercase tracking-wider">URL</th>
                {ALL_PAGES.map((page) => (
                  <th key={page} className="px-3 py-3 text-center text-xs font-semibold text-white/50 uppercase tracking-wider whitespace-nowrap">
                    {page}
                  </th>
                ))}
                <th className="px-3 py-3 text-center text-xs font-semibold text-white/50 uppercase tracking-wider">Status</th>
              </tr>
            </thead>
            <tbody>
              {founders.map((slug) => {
                const pages = perms[slug] || []
                const subdomain = slug.replace(/_/g, '-')
                return (
                  <tr key={slug} className="border-b border-white/5 hover:bg-white/[0.02]">
                    <td className="px-4 py-3 font-medium text-white">{slug}</td>
                    <td className="px-4 py-3">
                      <a
                        href={`https://${subdomain}.tagent.club`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-white/50 hover:text-white underline"
                      >
                        {subdomain}.tagent.club
                      </a>
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
                        <span className="text-xs text-white/30">{pages.length} pages</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {founders.length === 0 && (
        <div className="mt-8 text-center text-sm text-white/50">
          No founders configured. Add founders to <code className="rounded bg-white/10 px-1.5 py-0.5 text-xs">config/founder-permissions.yaml</code>.
        </div>
      )}
    </div>
  )
}
