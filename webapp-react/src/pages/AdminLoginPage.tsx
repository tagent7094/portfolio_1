import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Shield } from 'lucide-react'
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
      setError('Invalid admin password')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-black px-4">
      <div className="w-full max-w-sm animate-slide-up">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white">
            <Shield size={22} className="text-black" />
          </div>
          <h1 className="font-[var(--font-display)] text-xl font-semibold text-white">Admin Panel</h1>
          <p className="text-xs text-white/50">Digital DNA — Developer Controls</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 rounded-2xl border border-white/10 bg-white/[0.03] p-6">
          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.1em] text-white/50">
              Admin Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-black/60 px-3 py-2 text-sm text-white focus:border-white/30 focus:outline-none"
              autoFocus
              required
            />
          </div>

          {error && (
            <div className="text-xs text-white/80">{error}</div>
          )}

          <button
            type="submit"
            disabled={submitting || !password}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-white px-3 py-2.5 text-sm font-semibold text-black hover:bg-white/90 disabled:opacity-40"
          >
            {submitting ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
            {submitting ? 'Signing in...' : 'Access Admin Panel'}
          </button>
        </form>
      </div>
    </div>
  )
}
