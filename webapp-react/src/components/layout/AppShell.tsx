import { useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Sparkles,
  Wand2,
  GitFork,
  BarChart3,
  Workflow,
  Clock,
  Settings,
  LogOut,
  KeyRound,
  Loader2,
  X,
} from 'lucide-react'
import FounderSelector from './FounderSelector'
import clsx from 'clsx'
import { useAuthStore } from '../../store/useAuthStore'
import { getSubdomainSlug } from '../../utils/subdomain'

const NAV_ITEMS = [
  { to: '/', id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/generate', id: 'generate', label: 'Generate', icon: Sparkles },
  { to: '/customize', id: 'customize', label: 'Customize', icon: Wand2 },
  { to: '/graph', id: 'graph', label: 'Graph', icon: GitFork },
  { to: '/coverage', id: 'coverage', label: 'Coverage', icon: BarChart3 },
  { to: '/workflow', id: 'workflow', label: 'Workflow', icon: Workflow },
  { to: '/history', id: 'history', label: 'History', icon: Clock },
  { to: '/config', id: 'config', label: 'Config', icon: Settings },
] as const

export default function AppShell() {
  const navigate = useNavigate()
  const { logout, displayName, allowedPages, changePassword, error } = useAuthStore()
  const isScoped = getSubdomainSlug() !== null
  const [showPwModal, setShowPwModal] = useState(false)
  const [pwCurrent, setPwCurrent] = useState('')
  const [pwNew, setPwNew] = useState('')
  const [pwConfirm, setPwConfirm] = useState('')
  const [pwLoading, setPwLoading] = useState(false)
  const [pwSuccess, setPwSuccess] = useState(false)
  const [pwError, setPwError] = useState('')

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const handleChangePassword = async () => {
    setPwError('')
    if (pwNew !== pwConfirm) {
      setPwError('Passwords do not match')
      return
    }
    if (pwNew.length < 6) {
      setPwError('Password must be at least 6 characters')
      return
    }
    setPwLoading(true)
    const ok = await changePassword(pwCurrent, pwNew)
    setPwLoading(false)
    if (ok) {
      setPwSuccess(true)
      setTimeout(() => {
        setShowPwModal(false)
        setPwSuccess(false)
        setPwCurrent('')
        setPwNew('')
        setPwConfirm('')
      }, 1500)
    } else {
      setPwError(error || 'Failed to change password')
    }
  }

  // Filter nav items by allowed pages
  const visibleNavItems = isScoped
    ? NAV_ITEMS.filter(item => allowedPages.includes(item.id))
    : NAV_ITEMS

  return (
    <div className="flex h-screen flex-col bg-black text-white">
      {/* Header */}
      <header className="relative flex items-center justify-between border-b border-white/10 px-6 py-3">
        <div className="flex items-center gap-3.5">
          <div className="relative h-8 w-8">
            <div className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-white">
              <span className="font-[var(--font-display)] text-[13px] font-bold tracking-tight text-black">DD</span>
            </div>
          </div>
          <div>
            <h1 className="font-[var(--font-display)] text-[15px] font-semibold tracking-tight text-white">
              Digital DNA
            </h1>
            {isScoped && displayName && (
              <p className="text-[10px] font-medium text-white/50 leading-none mt-0.5">{displayName}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {!isScoped && <FounderSelector />}
          {isScoped && (
            <>
              <button
                onClick={() => setShowPwModal(true)}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[12px] font-medium text-white/80 transition-colors hover:bg-white/10 hover:text-white"
                title="Change password"
              >
                <KeyRound size={13} />
              </button>
              <button
                onClick={handleLogout}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[12px] font-medium text-white/80 transition-colors hover:bg-white/10 hover:text-white"
                title="Sign out"
              >
                <LogOut size={13} />
                Sign out
              </button>
            </>
          )}
        </div>
      </header>

      {/* Nav */}
      <nav className="flex gap-0.5 border-b border-white/10 px-5">
        {visibleNavItems.map(({ to, label, icon: Icon, ...rest }) => (
          <NavLink
            key={to}
            to={to}
            end={'end' in rest}
            className={({ isActive }) =>
              clsx(
                'relative flex items-center gap-2 px-3.5 py-2.5 text-[13px] font-medium transition-all duration-200',
                isActive
                  ? 'text-white'
                  : 'text-white/50 hover:text-white/80',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={15} />
                {label}
                {isActive && (
                  <span className="absolute inset-x-2 -bottom-px h-[2px] rounded-full bg-white" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Content */}
      <main className="relative flex-1 overflow-auto p-5 bg-black">
        <Outlet />
      </main>

      {/* Change Password Modal */}
      {showPwModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-black p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">Change Password</h2>
              <button onClick={() => { setShowPwModal(false); setPwError(''); setPwSuccess(false) }} className="text-white/50 hover:text-white">
                <X size={16} />
              </button>
            </div>

            {pwSuccess ? (
              <div className="py-6 text-center text-sm text-white">Password changed successfully</div>
            ) : (
              <div className="space-y-3">
                <input
                  type="password"
                  placeholder="Current password"
                  value={pwCurrent}
                  onChange={(e) => setPwCurrent(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white placeholder-white/30 focus:border-white/30 focus:outline-none"
                  autoFocus
                />
                <input
                  type="password"
                  placeholder="New password"
                  value={pwNew}
                  onChange={(e) => setPwNew(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white placeholder-white/30 focus:border-white/30 focus:outline-none"
                />
                <input
                  type="password"
                  placeholder="Confirm new password"
                  value={pwConfirm}
                  onChange={(e) => setPwConfirm(e.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white placeholder-white/30 focus:border-white/30 focus:outline-none"
                />
                {pwError && (
                  <div className="text-xs text-white/80">{pwError}</div>
                )}
                <button
                  onClick={handleChangePassword}
                  disabled={pwLoading || !pwCurrent || !pwNew || !pwConfirm}
                  className="flex w-full items-center justify-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-semibold text-black hover:bg-white/90 disabled:opacity-40"
                >
                  {pwLoading ? <Loader2 size={14} className="animate-spin" /> : null}
                  {pwLoading ? 'Changing...' : 'Change Password'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
