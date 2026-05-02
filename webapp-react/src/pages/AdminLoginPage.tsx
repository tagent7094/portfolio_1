import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Shield, ArrowRight } from 'lucide-react'
import { apiPost } from '../api/client'

export default function AdminLoginPage() {
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!password) return
    setSubmitting(true)
    setError('')
    try {
      await apiPost('/api/admin/login', { password })
      navigate('/admin', { replace: true })
    } catch {
      setError('Incorrect admin password')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grain relative flex min-h-screen items-center justify-center bg-[var(--page-bg)] px-4">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-[35%] h-[400px] w-[400px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/[0.012] blur-[100px]" />
      </div>

      <div className="relative z-10 w-full max-w-[340px] animate-slide-up">
        <div className="mb-10 text-center">
          <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--surface-3)] shadow-[var(--shadow-md)]">
            <Shield size={20} className="text-[var(--text-secondary)]" />
          </div>
          <h1 className="font-[var(--font-display)] text-[20px] font-bold tracking-tight text-[var(--text-primary)]">
            Admin Panel
          </h1>
          <p className="mt-1 text-[13px] text-[var(--text-muted)]">
            Developer access · Digital DNA
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-3 rounded-2xl border border-[var(--border-1)] bg-[var(--surface-1)] p-6 shadow-[var(--shadow-lg)]"
        >
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
              Admin Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="field"
              autoFocus
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
            disabled={submitting || !password}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-white py-2.5 text-[13.5px] font-semibold text-black transition-all hover:bg-white/92 disabled:opacity-40 disabled:cursor-not-allowed mt-2"
          >
            {submitting
              ? <Loader2 size={15} className="animate-spin" />
              : <ArrowRight size={15} />
            }
            {submitting ? 'Verifying…' : 'Access Admin'}
          </button>
        </form>
      </div>
    </div>
  )
}
