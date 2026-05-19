import { useEffect, useState, type ReactNode } from 'react'
import { Lock, Loader2, AlertCircle } from 'lucide-react'

interface AuthStatus {
  authenticated: boolean
  subdomain: string | null
  enabled: boolean
}

/**
 * Wraps a subdomain-scoped page (asksharath, askrevsure, ...) in a password
 * gate when the backend says the subdomain has auth enabled. If
 * `enabled=false` (or there's no subdomain — e.g. local dev) the gate is
 * invisible and renders children directly.
 *
 * Cookie persistence on the backend means typical users authenticate once
 * and stay authenticated for 30 days.
 */
export default function SubdomainGate({ children, brandLabel }: { children: ReactNode; brandLabel?: string }) {
  const [status, setStatus] = useState<AuthStatus | null>(null)
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const checkMe = async () => {
    try {
      const res = await fetch('/api/subdomain/auth/me', { credentials: 'include' })
      const data: AuthStatus = await res.json()
      setStatus(data)
    } catch {
      // If the auth endpoint is unreachable, fail open — better than blocking
      // a working app on a transient network error.
      setStatus({ authenticated: true, subdomain: null, enabled: false })
    }
  }

  useEffect(() => { checkMe() }, [])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!password.trim() || !status?.subdomain) return
    setSubmitting(true)
    setError('')
    try {
      const res = await fetch('/api/subdomain/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subdomain: status.subdomain, password }),
      })
      if (!res.ok) {
        const detail = (await res.json().catch(() => null))?.detail || `Login failed (${res.status})`
        throw new Error(detail)
      }
      setPassword('')
      await checkMe()
    } catch (e: any) {
      setError(e?.message || 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  // Loading — show a quiet spinner instead of flashing the gate UI
  if (status === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--page-bg)]">
        <Loader2 className="animate-spin text-[var(--text-muted)]" size={24} />
      </div>
    )
  }

  // No gate required → render the page
  if (!status.enabled || status.authenticated) {
    return <>{children}</>
  }

  // Gate
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--page-bg)] px-6">
      <div className="w-full max-w-sm rounded-2xl border border-[var(--border-3)] bg-[var(--surface-2)] p-8 shadow-2xl">
        <div className="mb-5 flex items-center gap-3">
          <div className="rounded-full bg-[var(--surface-3)] p-2">
            <Lock size={18} className="text-[var(--text-muted)]" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">
              {brandLabel || (status.subdomain || 'site')}
            </h1>
            <p className="text-xs text-[var(--text-muted)]">Password required</p>
          </div>
        </div>

        <form onSubmit={handleLogin}>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter password"
            autoFocus
            className="w-full rounded-lg border border-[var(--border-3)] bg-[var(--surface-3)] px-3 py-2.5 text-sm font-mono"
          />
          {error && (
            <div className="mt-3 flex items-start gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-300">
              <AlertCircle size={12} className="mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <button
            type="submit"
            disabled={submitting || !password.trim()}
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-[var(--accent-fg)] disabled:opacity-50"
          >
            {submitting && <Loader2 size={14} className="animate-spin" />}
            Sign in
          </button>
        </form>

        <p className="mt-5 text-center text-xs text-[var(--text-muted)]">
          Access is invite-only. Contact your administrator if you need credentials.
        </p>
      </div>
    </div>
  )
}
