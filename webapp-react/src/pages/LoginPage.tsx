import { useState, useEffect, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Lock, Dna } from 'lucide-react'
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
    <div className="grain relative flex min-h-screen items-center justify-center bg-gray-950 px-4">
      {/* Ambient glow */}
      <div className="pointer-events-none absolute -top-40 left-1/2 h-80 w-80 -translate-x-1/2 rounded-full bg-indigo-600/10 blur-[100px]" />
      <div className="pointer-events-none absolute -bottom-40 left-1/3 h-80 w-80 rounded-full bg-violet-600/10 blur-[100px]" />

      <div className="relative w-full max-w-sm animate-slide-up">
        {/* Logo */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="relative h-12 w-12">
            <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 opacity-80 blur-[10px]" />
            <div className="relative flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-500/30">
              <Dna size={22} className="text-white" />
            </div>
          </div>
          <h1 className="font-[var(--font-display)] text-xl font-semibold tracking-tight text-gray-100">
            Digital DNA
          </h1>
          <p className="text-xs text-gray-500">
            {subdomain ? `Sign in to ${subdomain}.tagent.club` : 'Sign in'}
          </p>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="glass-panel-strong space-y-4 rounded-2xl p-6"
        >
          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.1em] text-gray-500">
              Founder slug
            </label>
            <input
              type="text"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              readOnly={!!subdomain}
              className="w-full rounded-lg border border-white/[0.06] bg-gray-950/50 px-3 py-2 text-sm text-gray-100 transition-colors focus:border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-500/15 disabled:opacity-50"
              placeholder="sharath"
              autoFocus={!subdomain}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.1em] text-gray-500">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-white/[0.06] bg-gray-950/50 px-3 py-2 text-sm text-gray-100 transition-colors focus:border-indigo-500/40 focus:outline-none focus:ring-1 focus:ring-indigo-500/15"
              autoFocus={!!subdomain}
              required
            />
          </div>

          {error && (
            <div className="rounded-lg border border-red-900/50 bg-red-950/30 px-3 py-2 text-xs text-red-400">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !slug || !password}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-indigo-600 to-indigo-500 px-3 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-500/15 transition-all hover:shadow-indigo-500/25 disabled:opacity-50"
          >
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <Lock size={14} />}
            {submitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <p className="mt-6 text-center text-[10px] text-gray-600">
          Access provided by Digital DNA team
        </p>
      </div>
    </div>
  )
}
