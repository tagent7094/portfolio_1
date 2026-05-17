import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Shield, LogOut, Loader2, KeyRound, Copy, CheckCircle2,
  RefreshCw, X, ExternalLink, FileSpreadsheet, Sparkles,
  Clock, Plus, Trash2, Power, Upload, Database, Search,
  ThumbsUp, MessageSquare, Repeat2, Star, ChevronDown,
  LayoutDashboard, GitFork, Merge, Mail, Send, Save, Cpu,
} from 'lucide-react'
import clsx from 'clsx'
import { apiGet, apiPost, apiPut, apiDelete, apiUpload } from '../api/client'
import { Button, Badge, Card, CardBody, Spinner } from '../components/ui'
import ModelsConfigPanel from '../components/config/ModelsConfigPanel'

const ALL_PAGES = ['dashboard', 'generate', 'content-studio', 'graph', 'coverage', 'workflow', 'history', 'config']

interface FounderProfile {
  slug: string; display_name: string; subdomain: string; url: string
  has_password: boolean; last_reset_at: string | null; pages: string[]; graph_path: string
}

interface Schedule {
  id: string; founder_slug: string; hour: number; minute: number
  days: string[]; n_sources: number; posts_per_source: number; creativity: number; effort: string
  enabled: boolean; created_at: string; last_run: string | null; last_status: string | null
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

  // Schedule state
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [showNewSchedule, setShowNewSchedule] = useState(false)
  const [newSched, setNewSched] = useState({ founder_slug: '', hour: 9, minute: 0, days: ['mon', 'tue', 'wed', 'thu', 'fri'], n_sources: 3, posts_per_source: 9, creativity: 0.5, effort: 'high' })
  const [savingSchedule, setSavingSchedule] = useState(false)

  const refreshSchedules = useCallback(async () => {
    try {
      const data = await apiGet<{ schedules: Schedule[] }>('/api/admin/schedules')
      setSchedules(data.schedules)
    } catch { /* ignore */ }
  }, [])

  const createSchedule = async () => {
    if (!newSched.founder_slug) return
    setSavingSchedule(true)
    try {
      await apiPost('/api/admin/schedules', newSched)
      await refreshSchedules()
      setShowNewSchedule(false)
    } catch { /* ignore */ }
    finally { setSavingSchedule(false) }
  }

  const toggleSchedule = async (id: string) => {
    try {
      await apiPost(`/api/admin/schedules/${id}/toggle`, {})
      await refreshSchedules()
    } catch { /* ignore */ }
  }

  const deleteSchedule = async (id: string) => {
    try {
      await apiDelete(`/api/admin/schedules/${id}`)
      await refreshSchedules()
    } catch { /* ignore */ }
  }

  // Server status
  const [serverStatus, setServerStatus] = useState<any>(null)
  const [schedulerStatus, setSchedulerStatus] = useState<{ running: boolean; tick_count: number; last_tick: string | null; enabled_count: number; total_count: number } | null>(null)
  const [runningNow, setRunningNow] = useState<string | null>(null)

  const refreshSchedulerStatus = useCallback(async () => {
    try { setSchedulerStatus(await apiGet('/api/admin/schedules/status')) } catch {}
  }, [])

  const runScheduleNow = async (id: string) => {
    setRunningNow(id)
    try {
      await apiPost(`/api/admin/schedules/${id}/run-now`, {})
      await refreshSchedules()
    } catch (err: any) { alert(`Failed: ${err?.message}`) }
    finally { setRunningNow(null) }
  }

  const refreshStatus = useCallback(async () => {
    try { setServerStatus(await apiGet<any>('/api/admin/server/status')) } catch {}
  }, [])

  // Viral repo state
  const [repoFiles, setRepoFiles] = useState<{ name: string; size_kb: number; post_count: number; active: boolean }[]>([])
  const [repoLoading, setRepoLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [combineMode, setCombineMode] = useState(false)
  const [combineSelected, setCombineSelected] = useState<Set<string>>(new Set())
  const [combineName, setCombineName] = useState('')
  const [combining, setCombining] = useState(false)
  const [activating, setActivating] = useState<string | null>(null)
  const uploadRef = useRef<HTMLInputElement>(null)

  // Viral post browser state
  const [vpSources, setVpSources] = useState<any[]>([])
  const [vpTotal, setVpTotal] = useState(0)
  const [vpLoading, setVpLoading] = useState(false)
  const [vpQuery, setVpQuery] = useState('')
  const [vpMinLikes, setVpMinLikes] = useState('')
  const [vpMaxLikes, setVpMaxLikes] = useState('')
  const [vpMinComments, setVpMinComments] = useState('')
  const [vpMaxComments, setVpMaxComments] = useState('')
  const [vpSortBy, setVpSortBy] = useState('engagement_score')
  const [vpFounder, setVpFounder] = useState('')
  const [vpPage, setVpPage] = useState(1)
  const [vpExpanded, setVpExpanded] = useState(false)
  const [vpSheet, setVpSheet] = useState('')
  const [vpSheets, setVpSheets] = useState<string[]>([])
  const [vpDeep, setVpDeep] = useState(false)

  // Email notification settings
  const [notifyConfig, setNotifyConfig] = useState<{ recipients: string; subject_template: string; body_header: string; body_footer: string; enabled: boolean } | null>(null)
  const [notifySaving, setNotifySaving] = useState(false)
  const [notifySaved, setNotifySaved] = useState(false)
  const [notifyTesting, setNotifyTesting] = useState(false)

  const refreshNotifyConfig = useCallback(async () => {
    try {
      const cfg = await apiGet<{ recipients: string; subject_template: string; body_header: string; body_footer: string; enabled: boolean }>('/api/admin/notify/config')
      setNotifyConfig(cfg)
    } catch {}
  }, [])

  const saveNotifyConfig = async () => {
    if (!notifyConfig) return
    setNotifySaving(true)
    try {
      const updated = await apiPut<any>('/api/admin/notify/config', notifyConfig)
      setNotifyConfig(updated)
      setNotifySaved(true)
      setTimeout(() => setNotifySaved(false), 2000)
    } catch {}
    setNotifySaving(false)
  }

  const sendTestEmail = async () => {
    setNotifyTesting(true)
    try {
      await apiPost('/api/admin/notify/test', {})
      alert('Test email sent — check inbox')
    } catch (e: any) { alert(`Failed: ${e?.message}`) }
    setNotifyTesting(false)
  }

  const refreshRepos = useCallback(async () => {
    setRepoLoading(true)
    try {
      const data = await apiGet<{ files: any[] }>('/api/admin/viral-repos')
      setRepoFiles(data.files)
    } catch {}
    finally { setRepoLoading(false) }
  }, [])

  const handleRepoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await apiUpload('/api/admin/viral-repos/upload', file)
      await refreshRepos()
    } catch (err: any) { alert(`Upload failed: ${err?.message}`) }
    finally { setUploading(false); if (uploadRef.current) uploadRef.current.value = '' }
  }

  const handleRepoDelete = async (name: string) => {
    try {
      await apiDelete(`/api/admin/viral-repos/${encodeURIComponent(name)}`)
      await refreshRepos()
    } catch (err: any) { alert(err?.message) }
  }

  const handleRepoActivate = async (name: string) => {
    setActivating(name)
    try {
      await apiPost('/api/admin/viral-repos/activate', { filename: name })
      await refreshRepos()
    } catch (err: any) { alert(err?.message) }
    finally { setActivating(null) }
  }

  const handleCombine = async () => {
    if (combineSelected.size < 2 || !combineName.trim()) return
    setCombining(true)
    try {
      await apiPost('/api/admin/viral-repos/combine', { files: Array.from(combineSelected), output_name: combineName.trim() })
      await refreshRepos()
      setCombineMode(false)
      setCombineSelected(new Set())
      setCombineName('')
    } catch (err: any) { alert(err?.message) }
    finally { setCombining(false) }
  }

  const fetchViralPosts = useCallback(async () => {
    setVpLoading(true)
    try {
      const params = new URLSearchParams()
      if (vpQuery) params.set('q', vpQuery)
      if (vpMinLikes) params.set('min_likes', vpMinLikes)
      if (vpMaxLikes) params.set('max_likes', vpMaxLikes)
      if (vpMinComments) params.set('min_comments', vpMinComments)
      if (vpMaxComments) params.set('max_comments', vpMaxComments)
      if (vpSheet) params.set('source_sheet', vpSheet)
      params.set('limit', '20')
      params.set('offset', String((vpPage - 1) * 20))

      let data: any
      if (vpSortBy === 'best_match' && vpFounder) {
        params.set('page', String(vpPage))
        params.set('page_size', '20')
        const storedKey = localStorage.getItem('asksharath_api_key') || ''
        const hdrs: Record<string, string> = {}
        if (vpDeep && storedKey) {
          params.set('deep', 'true')
          hdrs['x-rerank-api-key'] = storedKey
        }
        data = await apiGet(`/api/viral-posts/best-match/${vpFounder}?${params}`, hdrs)
      } else {
        params.set('sort_by', vpSortBy)
        data = await apiGet(`/api/viral-sources?${params}`)
      }
      setVpSources(data.sources || [])
      setVpTotal(data.total || 0)
    } catch {}
    finally { setVpLoading(false) }
  }, [vpQuery, vpMinLikes, vpMaxLikes, vpMinComments, vpMaxComments, vpSortBy, vpFounder, vpPage, vpSheet, vpDeep])

  useEffect(() => {
    if (vpExpanded) {
      fetchViralPosts()
      apiGet<{ sheets: string[] }>('/api/viral-sources/sheets').then(d => setVpSheets(d.sheets)).catch(() => {})
    }
  }, [vpExpanded, fetchViralPosts])

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
      .then(() => { setAuthed(true); refresh(); refreshSchedules(); refreshRepos(); refreshStatus(); refreshSchedulerStatus(); refreshNotifyConfig() })
      .catch(() => { setAuthed(false); navigate('/admin/login', { replace: true }) })
  }, [navigate, refresh, refreshSchedules, refreshRepos, refreshSchedulerStatus, refreshNotifyConfig])

  useEffect(() => {
    if (!authed) return
    const id = setInterval(() => { refresh(); refreshSchedulerStatus() }, 10000)
    return () => clearInterval(id)
  }, [authed, refresh, refreshSchedulerStatus])

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

      {/* System status */}
      {(serverStatus || schedulerStatus) && (
        <div className="mb-4 flex items-center gap-4 flex-wrap text-[11px]" style={{ color: 'var(--text-muted)' }}>
          {serverStatus && (
            <>
              <div className="flex items-center gap-1.5">
                <LayoutDashboard size={11} style={{ color: 'var(--text-faint)' }} />
                <span>Uptime: {serverStatus.uptime_seconds < 3600
                  ? `${Math.floor(serverStatus.uptime_seconds / 60)}m`
                  : `${Math.floor(serverStatus.uptime_seconds / 3600)}h ${Math.floor((serverStatus.uptime_seconds % 3600) / 60)}m`
                }</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Sparkles size={11} style={{ color: 'var(--text-faint)' }} />
                <span>{serverStatus.active_tasks} active task{serverStatus.active_tasks !== 1 ? 's' : ''}</span>
              </div>
              {serverStatus.memory_mb && (
                <span>RAM: {serverStatus.memory_mb} MB</span>
              )}
              <span style={{ color: 'var(--text-faint)' }}>Python {serverStatus.python_version}</span>
            </>
          )}
          {schedulerStatus && (
            <>
              <div className="flex items-center gap-1.5">
                <Power size={11} style={{ color: schedulerStatus.running ? '#22c55e' : '#ef4444' }} />
                <span>Scheduler: {schedulerStatus.running ? 'running' : 'stopped'} ({schedulerStatus.enabled_count}/{schedulerStatus.total_count})</span>
              </div>
              <span style={{ color: 'var(--text-faint)' }}>
                tick #{schedulerStatus.tick_count}{schedulerStatus.last_tick && ` · ${formatTimeAgo(schedulerStatus.last_tick)}`}
              </span>
            </>
          )}
        </div>
      )}

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
                      <div className="mt-1.5 flex items-center gap-3 flex-wrap">
                        <button
                          onClick={() => navigate(`/admin/founders/${slug}`)}
                          className="inline-flex items-center gap-1 text-[11px] text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
                        >
                          <FileSpreadsheet size={11} /> Packs
                        </button>
                        <button
                          onClick={() => navigate(`/admin/founders/${slug}?generate=1`)}
                          className="inline-flex items-center gap-1 text-[11px] text-violet-400 transition-colors hover:text-violet-300"
                        >
                          <Sparkles size={11} /> Generate
                        </button>
                        <a
                          href={`${url}/`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] text-sky-400 transition-colors hover:text-sky-300"
                        >
                          <LayoutDashboard size={11} /> Dashboard
                        </a>
                        <a
                          href={`${url}/graph`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[11px] text-emerald-400 transition-colors hover:text-emerald-300"
                        >
                          <GitFork size={11} /> Graph
                        </a>
                      </div>
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

      {/* Schedules */}
      <Card className="mt-6">
        <div className="flex items-center justify-between border-b border-[var(--border-1)] px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <Clock size={14} className="text-[var(--text-secondary)]" />
            <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">Scheduled Generation</h2>
            <span className="text-[11px] text-[var(--text-muted)]">{schedules.length} schedule{schedules.length !== 1 ? 's' : ''}</span>
          </div>
          <Button variant="primary" size="xs" onClick={() => { setShowNewSchedule(true); if (profiles.length) setNewSched(s => ({ ...s, founder_slug: s.founder_slug || profiles[0].slug })) }} icon={<Plus size={12} />}>
            Add
          </Button>
        </div>

        {schedules.length === 0 && !showNewSchedule && (
          <CardBody>
            <p className="py-4 text-center text-[12px] text-[var(--text-muted)]">
              No schedules configured. Add one to auto-generate posts on a recurring basis.
            </p>
          </CardBody>
        )}

        {schedules.length > 0 && (
          <div className="divide-y divide-[var(--border-2)]">
            {schedules.map(s => (
              <div key={s.id} className="flex items-center gap-4 px-5 py-3 text-[12px]">
                <button onClick={() => toggleSchedule(s.id)} title={s.enabled ? 'Disable' : 'Enable'}>
                  <Power size={14} className={s.enabled ? 'text-[var(--success)]' : 'text-[var(--text-faint)]'} />
                </button>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-[var(--text-primary)]">{s.founder_slug}</span>
                    <span className="text-[var(--text-muted)]">
                      {String(s.hour).padStart(2, '0')}:{String(s.minute).padStart(2, '0')} IST
                    </span>
                    <span className="text-[10px] text-[var(--text-faint)]">
                      {s.days.map(d => d.slice(0, 3)).join(', ')}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10px] text-[var(--text-faint)]">
                    {s.n_sources} sources · {s.posts_per_source ?? 9} posts/src · {s.effort} effort
                    {s.last_run && ` · last run ${formatTimeAgo(s.last_run)}`}
                    {s.last_status && ` (${s.last_status})`}
                  </div>
                </div>
                <Button
                  variant="secondary" size="xs"
                  onClick={() => runScheduleNow(s.id)}
                  disabled={runningNow === s.id}
                  loading={runningNow === s.id}
                  icon={<Sparkles size={11} />}
                >
                  Run Now
                </Button>
                <button onClick={() => deleteSchedule(s.id)} className="text-[var(--text-faint)] hover:text-[var(--error)] transition-colors">
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}

        {showNewSchedule && (
          <CardBody className="border-t border-[var(--border-2)]">
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Founder</label>
                <select
                  value={newSched.founder_slug}
                  onChange={e => setNewSched(s => ({ ...s, founder_slug: e.target.value }))}
                  className="field w-full text-[12px]"
                >
                  <option value="">Select...</option>
                  {profiles.map(p => <option key={p.slug} value={p.slug}>{p.display_name}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Time (IST)</label>
                <div className="flex gap-1">
                  <input type="number" min={0} max={23} value={newSched.hour} onChange={e => setNewSched(s => ({ ...s, hour: Number(e.target.value) }))} className="field w-14 text-[12px] text-center" />
                  <span className="text-[var(--text-muted)] self-center">:</span>
                  <input type="number" min={0} max={59} step={15} value={newSched.minute} onChange={e => setNewSched(s => ({ ...s, minute: Number(e.target.value) }))} className="field w-14 text-[12px] text-center" />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Sources</label>
                <input type="number" min={1} max={10} value={newSched.n_sources} onChange={e => setNewSched(s => ({ ...s, n_sources: Number(e.target.value) }))} className="field w-full text-[12px]" />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Posts/Source</label>
                <input type="number" min={1} max={9} value={newSched.posts_per_source} onChange={e => setNewSched(s => ({ ...s, posts_per_source: Number(e.target.value) }))} className="field w-full text-[12px]" />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Effort</label>
                <select value={newSched.effort} onChange={e => setNewSched(s => ({ ...s, effort: e.target.value }))} className="field w-full text-[12px]">
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              {['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].map(d => (
                <button
                  key={d}
                  onClick={() => setNewSched(s => ({
                    ...s,
                    days: s.days.includes(d) ? s.days.filter(x => x !== d) : [...s.days, d],
                  }))}
                  className={clsx(
                    'rounded-md px-2 py-1 text-[10px] font-medium uppercase transition-colors',
                    newSched.days.includes(d)
                      ? 'bg-white text-black'
                      : 'bg-[var(--surface-3)] text-[var(--text-faint)]',
                  )}
                >
                  {d}
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-2">
              <Button variant="primary" size="sm" onClick={createSchedule} disabled={savingSchedule || !newSched.founder_slug} loading={savingSchedule}>
                Create Schedule
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setShowNewSchedule(false)}>
                Cancel
              </Button>
            </div>
          </CardBody>
        )}
      </Card>

      {/* Viral Repo Manager */}
      <Card className="mt-6">
        <div className="flex items-center justify-between border-b border-[var(--border-1)] px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <Database size={14} className="text-[var(--text-secondary)]" />
            <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">Viral Post Repository</h2>
            <span className="text-[11px] text-[var(--text-muted)]">{repoFiles.length} file{repoFiles.length !== 1 ? 's' : ''}</span>
          </div>
          <div className="flex items-center gap-2">
            {combineMode ? (
              <>
                <input
                  type="text"
                  value={combineName}
                  onChange={e => setCombineName(e.target.value)}
                  placeholder="combined-name"
                  className="field text-[11px] w-36"
                />
                <Button variant="primary" size="xs" onClick={handleCombine} disabled={combining || combineSelected.size < 2 || !combineName.trim()} loading={combining} icon={<Merge size={11} />}>
                  Merge {combineSelected.size}
                </Button>
                <Button variant="ghost" size="xs" onClick={() => { setCombineMode(false); setCombineSelected(new Set()) }}>
                  Cancel
                </Button>
              </>
            ) : (
              <>
                <Button variant="secondary" size="xs" onClick={() => setCombineMode(true)} icon={<Merge size={11} />}>
                  Combine
                </Button>
                <input ref={uploadRef} type="file" accept=".csv,.xlsx" onChange={handleRepoUpload} className="hidden" />
                <Button variant="primary" size="xs" onClick={() => uploadRef.current?.click()} disabled={uploading} loading={uploading} icon={<Upload size={11} />}>
                  Upload
                </Button>
              </>
            )}
          </div>
        </div>

        {repoLoading ? (
          <CardBody><Loader2 size={16} className="mx-auto animate-spin text-[var(--text-muted)]" /></CardBody>
        ) : repoFiles.length === 0 ? (
          <CardBody>
            <p className="py-4 text-center text-[12px] text-[var(--text-muted)]">
              No viral post files found. Upload a CSV or XLSX file to get started.
            </p>
          </CardBody>
        ) : (
          <div className="divide-y divide-[var(--border-2)]">
            {repoFiles.map(f => (
              <div key={f.name} className="flex items-center gap-4 px-5 py-3 text-[12px]">
                {combineMode && (
                  <input
                    type="checkbox"
                    checked={combineSelected.has(f.name)}
                    onChange={() => {
                      const next = new Set(combineSelected)
                      if (next.has(f.name)) next.delete(f.name)
                      else next.add(f.name)
                      setCombineSelected(next)
                    }}
                    className="accent-white"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-[var(--text-primary)] truncate">{f.name}</span>
                    {f.active && <Badge variant="default">Active</Badge>}
                  </div>
                  <span className="text-[10px] text-[var(--text-faint)]">
                    {f.size_kb} KB · {f.post_count.toLocaleString()} posts
                  </span>
                </div>
                {!combineMode && (
                  <div className="flex items-center gap-2">
                    {!f.active && (
                      <Button
                        variant="secondary" size="xs"
                        onClick={() => handleRepoActivate(f.name)}
                        disabled={activating === f.name}
                        loading={activating === f.name}
                        icon={<Power size={11} />}
                      >
                        Activate
                      </Button>
                    )}
                    {!f.active && (
                      <button onClick={() => handleRepoDelete(f.name)} className="text-[var(--text-faint)] hover:text-[var(--error)] transition-colors">
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Viral Post Browser */}
      <Card className="mt-6">
        <button
          onClick={() => setVpExpanded(v => !v)}
          className="flex w-full items-center justify-between px-5 py-3.5 text-left"
        >
          <div className="flex items-center gap-2.5">
            <Search size={14} className="text-[var(--text-secondary)]" />
            <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">Viral Post Browser</h2>
            <span className="text-[11px] text-[var(--text-muted)]">{vpTotal.toLocaleString()} posts</span>
          </div>
          <ChevronDown size={14} className={clsx('text-[var(--text-muted)] transition-transform', vpExpanded && 'rotate-180')} />
        </button>

        {vpExpanded && (
          <>
            <div className="border-t border-[var(--border-2)] px-5 py-3 space-y-3">
              {/* Search + Founder selector */}
              <div className="flex gap-2 flex-wrap">
                <div className="relative flex-1 min-w-[200px]">
                  <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)]" />
                  <input
                    type="text"
                    value={vpQuery}
                    onChange={e => { setVpQuery(e.target.value); setVpPage(1) }}
                    placeholder="Search posts..."
                    className="field w-full pl-8 text-[12px]"
                  />
                </div>
                <select
                  value={vpFounder}
                  onChange={e => { setVpFounder(e.target.value); setVpPage(1) }}
                  className="field text-[12px] w-40"
                >
                  <option value="">All founders</option>
                  {profiles.map(p => <option key={p.slug} value={p.slug}>{p.display_name}</option>)}
                </select>
                <select
                  value={vpSortBy}
                  onChange={e => { setVpSortBy(e.target.value); setVpPage(1) }}
                  className="field text-[12px] w-40"
                >
                  <option value="engagement_score">Engagement</option>
                  <option value="likes">Likes</option>
                  <option value="comments">Comments</option>
                  <option value="reposts">Reposts</option>
                  {vpFounder && <option value="best_match">Best Match</option>}
                </select>
                {vpSheets.length > 0 && (
                  <select
                    value={vpSheet}
                    onChange={e => { setVpSheet(e.target.value); setVpPage(1) }}
                    className="field text-[12px] w-52"
                  >
                    <option value="">All sheets ({vpSheets.length})</option>
                    {vpSheets.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                )}
                {vpSortBy === 'best_match' && vpFounder && (
                  <button
                    onClick={() => {
                      if (!localStorage.getItem('asksharath_api_key') && !vpDeep) {
                        alert('Set your Anthropic API key in Config page first')
                        return
                      }
                      setVpDeep(d => !d)
                      setVpPage(1)
                    }}
                    className={`rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                      vpDeep
                        ? 'border-amber-500/50 bg-amber-500/10 text-amber-400'
                        : 'border-[var(--border-1)] bg-[var(--surface-3)] text-[var(--text-muted)]'
                    }`}
                  >
                    Deep Match {vpDeep ? 'ON' : 'OFF'}
                  </button>
                )}
              </div>

              {/* Engagement filters */}
              <div className="flex gap-3 flex-wrap text-[11px]">
                <div className="flex items-center gap-1.5">
                  <ThumbsUp size={11} className="text-[var(--text-faint)]" />
                  <input type="number" placeholder="Min" value={vpMinLikes} onChange={e => { setVpMinLikes(e.target.value); setVpPage(1) }} className="field w-16 text-[11px] text-center" />
                  <span className="text-[var(--text-faint)]">–</span>
                  <input type="number" placeholder="Max" value={vpMaxLikes} onChange={e => { setVpMaxLikes(e.target.value); setVpPage(1) }} className="field w-16 text-[11px] text-center" />
                </div>
                <div className="flex items-center gap-1.5">
                  <MessageSquare size={11} className="text-[var(--text-faint)]" />
                  <input type="number" placeholder="Min" value={vpMinComments} onChange={e => { setVpMinComments(e.target.value); setVpPage(1) }} className="field w-16 text-[11px] text-center" />
                  <span className="text-[var(--text-faint)]">–</span>
                  <input type="number" placeholder="Max" value={vpMaxComments} onChange={e => { setVpMaxComments(e.target.value); setVpPage(1) }} className="field w-16 text-[11px] text-center" />
                </div>
                <Button variant="secondary" size="xs" onClick={() => { setVpPage(1); fetchViralPosts() }} icon={<Search size={11} />}>
                  Search
                </Button>
              </div>
            </div>

            {/* Results */}
            <div className="border-t border-[var(--border-2)]">
              {vpLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 size={16} className="animate-spin text-[var(--text-muted)]" />
                </div>
              ) : vpSources.length === 0 ? (
                <div className="py-8 text-center text-[12px] text-[var(--text-muted)]">No posts found</div>
              ) : (
                <div className="divide-y divide-[var(--border-2)]">
                  {vpSources.map((src: any) => (
                    <div key={src.id} className="px-5 py-3">
                      <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed line-clamp-3">
                        {src.content}
                      </p>
                      <div className="mt-2 flex items-center gap-3 text-[10px] text-[var(--text-faint)] flex-wrap">
                        {src.likes > 0 && (
                          <span className="flex items-center gap-1"><ThumbsUp size={10} /> {src.likes.toLocaleString()}</span>
                        )}
                        {src.comments > 0 && (
                          <span className="flex items-center gap-1"><MessageSquare size={10} /> {src.comments.toLocaleString()}</span>
                        )}
                        {src.reposts > 0 && (
                          <span className="flex items-center gap-1"><Repeat2 size={10} /> {src.reposts.toLocaleString()}</span>
                        )}
                        {src.content_type && (
                          <span className="rounded bg-[var(--surface-3)] px-1.5 py-0.5">{src.content_type}</span>
                        )}
                        {src.source_sheet && (
                          <span className="rounded bg-violet-500/20 text-violet-300 px-1.5 py-0.5">{src.source_sheet}</span>
                        )}
                        {src.match_score != null && (
                          <span className="flex items-center gap-1 text-amber-400">
                            <Star size={10} /> {src.match_score}% match
                            {src.topic_score != null && (
                              <span className="text-[9px] text-amber-400/70 ml-1">
                                T:{src.topic_score} M:{src.mechanics_score} A:{src.audience_score}
                              </span>
                            )}
                          </span>
                        )}
                        {src.match_reason && (
                          <span className="basis-full text-[10px] text-amber-400/60 italic mt-0.5">{src.match_reason}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Pagination */}
              {vpTotal > 20 && (
                <div className="flex items-center justify-between border-t border-[var(--border-2)] px-5 py-2.5 text-[11px]">
                  <span className="text-[var(--text-faint)]">
                    Page {vpPage} of {Math.ceil(vpTotal / 20)}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setVpPage(p => Math.max(1, p - 1))}
                      disabled={vpPage <= 1}
                      className="rounded px-2 py-1 text-[var(--text-muted)] disabled:opacity-30 hover:bg-[var(--surface-3)]"
                    >
                      Prev
                    </button>
                    <button
                      onClick={() => setVpPage(p => p + 1)}
                      disabled={vpPage >= Math.ceil(vpTotal / 20)}
                      className="rounded px-2 py-1 text-[var(--text-muted)] disabled:opacity-30 hover:bg-[var(--surface-3)]"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </Card>

      {/* Email Notification Settings */}
      <Card>
        <CardBody>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-[14px] font-semibold text-[var(--text-primary)]">
              <Mail size={15} /> Email Notifications
            </div>
            <div className="flex items-center gap-2">
              {notifySaved && <span className="text-[12px] text-[var(--success)]">Saved</span>}
              <Button variant="secondary" size="xs" onClick={sendTestEmail} loading={notifyTesting} icon={<Send size={12} />}>
                Test
              </Button>
              <Button variant="primary" size="xs" onClick={saveNotifyConfig} loading={notifySaving} icon={<Save size={12} />}>
                Save
              </Button>
            </div>
          </div>
          {notifyConfig ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <label className="text-[12px] text-[var(--text-secondary)] w-24 shrink-0">Enabled</label>
                <button
                  onClick={() => setNotifyConfig({ ...notifyConfig, enabled: !notifyConfig.enabled })}
                  className={clsx('relative w-10 h-5 rounded-full transition-colors', notifyConfig.enabled ? 'bg-[var(--success)]' : 'bg-[var(--surface-4)]')}
                >
                  <div className={clsx('absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all', notifyConfig.enabled ? 'left-5' : 'left-0.5')} />
                </button>
              </div>
              <div className="flex items-start gap-3">
                <label className="text-[12px] text-[var(--text-secondary)] w-24 shrink-0 pt-2">Recipients</label>
                <textarea
                  value={notifyConfig.recipients}
                  onChange={e => setNotifyConfig({ ...notifyConfig, recipients: e.target.value })}
                  rows={2}
                  placeholder="email1@example.com, email2@example.com"
                  className="flex-1 rounded-lg border border-[var(--border-1)] bg-[var(--surface-3)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none resize-none"
                />
              </div>
              <div className="flex items-center gap-3">
                <label className="text-[12px] text-[var(--text-secondary)] w-24 shrink-0">Subject</label>
                <input
                  value={notifyConfig.subject_template}
                  onChange={e => setNotifyConfig({ ...notifyConfig, subject_template: e.target.value })}
                  placeholder="[Tagent] Batch ready — {founder} ({posts} posts)"
                  className="flex-1 rounded-lg border border-[var(--border-1)] bg-[var(--surface-3)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none"
                />
              </div>
              <div className="flex items-center gap-3">
                <label className="text-[12px] text-[var(--text-secondary)] w-24 shrink-0">Header</label>
                <input
                  value={notifyConfig.body_header}
                  onChange={e => setNotifyConfig({ ...notifyConfig, body_header: e.target.value })}
                  placeholder="Batch Ready"
                  className="flex-1 rounded-lg border border-[var(--border-1)] bg-[var(--surface-3)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none"
                />
              </div>
              <div className="flex items-start gap-3">
                <label className="text-[12px] text-[var(--text-secondary)] w-24 shrink-0 pt-2">Footer</label>
                <textarea
                  value={notifyConfig.body_footer}
                  onChange={e => setNotifyConfig({ ...notifyConfig, body_footer: e.target.value })}
                  rows={2}
                  placeholder="Optional footer text for the email"
                  className="flex-1 rounded-lg border border-[var(--border-1)] bg-[var(--surface-3)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none resize-none"
                />
              </div>
              <div className="text-[11px] text-[var(--text-muted)] pl-[108px]">
                Subject variables: {'{'}founder{'}'}, {'{'}posts{'}'}, {'{'}trigger{'}'}, {'{'}date{'}'}
              </div>
            </div>
          ) : (
            <div className="text-[13px] text-[var(--text-muted)]">Loading notification settings...</div>
          )}
        </CardBody>
      </Card>

      {/* Models & Providers (admin defaults — per-task) */}
      <Card>
        <CardBody>
          <div className="flex items-center gap-2 mb-3 text-[14px] font-semibold text-[var(--text-primary)]">
            <Cpu size={15} /> Models & Providers
            <span className="ml-2 text-[11px] font-normal text-[var(--text-muted)]">
              Admin defaults for every pipeline task. Founders can override these on their /config page.
            </span>
          </div>
          <ModelsConfigPanel mode="admin" />
        </CardBody>
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
