import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, ArrowRight } from 'lucide-react'
import { useAuthStore } from '../store/useAuthStore'
import { getSubdomainSlug } from '../utils/subdomain'

export default function LoginPage() {
  const navigate = useNavigate()
  const subdomain = getSubdomainSlug()
  const { status, login, error } = useAuthStore()
  const [slug, setSlug] = useState(subdomain || '')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (status === 'authed') navigate('/', { replace: true })
  }, [status, navigate])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!slug || !password) return
    setSubmitting(true)
    const ok = await login(slug, password)
    setSubmitting(false)
    if (ok) navigate('/', { replace: true })
  }

  return (
    <div className="grain relative flex min-h-screen items-center justify-center bg-[var(--page-bg)] px-4">
      {/* Background ambient */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-[30%] h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/[0.012] blur-[120px]" />
        <div className="absolute left-1/2 top-1/2 h-[200px] w-[200px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/[0.02] blur-[60px]" />
      </div>

      <div className="relative z-10 w-full max-w-[360px] animate-slide-up">
        {/* Wordmark */}
        <div className="mb-10 text-center">
          <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-white shadow-[0_0_0_1px_rgba(255,255,255,0.2),0_4px_24px_rgba(255,255,255,0.06)]">
            <span className="font-[var(--font-display)] text-base font-bold tracking-tight text-black">DD</span>
          </div>
          <h1 className="font-[var(--font-display)] text-[22px] font-bold tracking-tight text-[var(--text-primary)]">
            Digital DNA
          </h1>
          <p className="mt-1 text-[13px] text-[var(--text-muted)]">
            {subdomain ? `Sign in to ${subdomain}.tagent.club` : 'Sign in to your workspace'}
          </p>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="space-y-3 rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-6 shadow-[var(--shadow-lg)]"
        >
          {!subdomain && (
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                Workspace
              </label>
              <input
                type="text"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                className="field"
                placeholder="sharath"
                autoFocus
                required
              />
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field"
              autoFocus={!!subdomain}
              required
            />
          </div>

          {error && (
            <div className="rounded-xl bg-[var(--error-dim)] px-4 py-3 text-[12.5px] text-[var(--error)]">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !slug || !password}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-white py-2.5 text-[13.5px] font-semibold text-black transition-all hover:bg-white/92 disabled:opacity-40 disabled:cursor-not-allowed mt-2"
          >
            {submitting
              ? <Loader2 size={15} className="animate-spin" />
              : <ArrowRight size={15} />
            }
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="mt-5 text-center text-[11px] text-[var(--text-muted)]">
          Access provided by the Tagent team
        </p>
      </div>
    </div>
  )
}
