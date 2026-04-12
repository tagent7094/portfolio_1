import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Lock } from 'lucide-react'
import { useAuthStore } from '../store/useAuthStore'
import { getSubdomainSlug } from '../utils/subdomain'

export default function LoginPage() {
  const navigate = useNavigate()
  const subdomain = getSubdomainSlug()
  const { status, login, error } = useAuthStore()
  const [slug, setSlug] = useState(subdomain || '')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // If already authed, kick to home
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
    <div className="grain relative flex min-h-screen items-center justify-center bg-black px-4">
      <div className="relative w-full max-w-sm animate-slide-up">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white">
            <span className="font-[var(--font-display)] text-lg font-bold tracking-tight text-black">DD</span>
          </div>
          <h1 className="font-[var(--font-display)] text-xl font-semibold tracking-tight text-white">
            Digital DNA
          </h1>
          <p className="text-xs text-white/50">
            {subdomain ? `Sign in to ${subdomain}.tagent.club` : 'Sign in'}
          </p>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-2xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-xl"
        >
          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.1em] text-white/50">
              Founder slug
            </label>
            <input
              type="text"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              readOnly={!!subdomain}
              className="w-full rounded-lg border border-white/10 bg-black/60 px-3 py-2 text-sm text-white transition-colors focus:border-white/30 focus:outline-none focus:ring-1 focus:ring-white/20 disabled:opacity-50 read-only:opacity-60"
              placeholder="sharath"
              autoFocus={!subdomain}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.1em] text-white/50">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-black/60 px-3 py-2 text-sm text-white transition-colors focus:border-white/30 focus:outline-none focus:ring-1 focus:ring-white/20"
              autoFocus={!!subdomain}
              required
            />
          </div>

          {error && (
            <div className="rounded-lg border border-white/20 bg-white/[0.04] px-3 py-2 text-xs text-white">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !slug || !password}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-white px-3 py-2.5 text-sm font-semibold text-black transition-all hover:bg-white/90 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <Lock size={14} />}
            {submitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <p className="mt-6 text-center text-[10px] text-white/40">
          Access provided by Digital DNA team
        </p>
      </div>
    </div>
  )
}
