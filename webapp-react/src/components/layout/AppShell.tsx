import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Sparkles, Wand2, GitFork, BarChart3,
  Workflow, Clock, Settings, LogOut, KeyRound, Loader2,
  X, Menu,
} from 'lucide-react'
import clsx from 'clsx'
import FounderSelector from './FounderSelector'
import { useAuthStore } from '../../store/useAuthStore'
import { getSubdomainSlug } from '../../utils/subdomain'

const NAV_ITEMS = [
  { to: '/',          id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/generate',  id: 'generate',  label: 'Generate',  icon: Sparkles },
  { to: '/customize', id: 'customize', label: 'Customize', icon: Wand2 },
  { to: '/graph',     id: 'graph',     label: 'Graph',     icon: GitFork },
  { to: '/coverage',  id: 'coverage',  label: 'Coverage',  icon: BarChart3 },
  { to: '/workflow',  id: 'workflow',  label: 'Workflow',  icon: Workflow },
  { to: '/history',   id: 'history',   label: 'History',   icon: Clock },
  { to: '/config',    id: 'config',    label: 'Config',    icon: Settings },
] as const

// ── Sidebar inner content (shared by desktop + mobile drawer) ────────────────
function SidebarContent({
  visibleItems,
  isScoped,
  displayName,
  onLogout,
  onChangePassword,
  onClose,
}: {
  visibleItems: typeof NAV_ITEMS[number][]
  isScoped: boolean
  displayName: string | null
  onLogout: () => void
  onChangePassword: () => void
  onClose?: () => void
}) {
  return (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div className="flex h-14 shrink-0 items-center justify-between px-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white shadow-[0_0_0_1px_rgba(255,255,255,0.15)]">
            <span className="font-[var(--font-display)] text-[11px] font-bold tracking-tight text-black select-none">DD</span>
          </div>
          <span className="font-[var(--font-display)] text-[13.5px] font-semibold tracking-tight text-[var(--text-primary)]">
            Digital DNA
          </span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)] lg:hidden"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {/* Nav items */}
      <nav className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
        {visibleItems.map(({ to, id, label, icon: Icon, ...rest }) => (
          <NavLink
            key={id}
            to={to}
            end={'end' in rest ? (rest as any).end : false}
            onClick={onClose}
            className={({ isActive }) =>
              clsx(
                'group flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] font-medium transition-all duration-100',
                isActive
                  ? 'bg-[var(--surface-3)] text-[var(--text-primary)]'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--surface-2)] hover:text-[var(--text-primary)]',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  size={16}
                  className={clsx(
                    'shrink-0 transition-colors',
                    isActive ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)] group-hover:text-[var(--text-secondary)]',
                  )}
                />
                {label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="shrink-0 border-t border-[var(--border-2)] px-2 py-2 space-y-0.5">
        {!isScoped && (
          <div className="px-2 py-2">
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">Founder</p>
            <FounderSelector />
          </div>
        )}

        {isScoped && displayName && (
          <div className="flex items-center gap-2.5 px-3 py-2.5">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--surface-4)] text-[11px] font-bold text-[var(--text-secondary)]">
              {displayName.charAt(0).toUpperCase()}
            </div>
            <span className="truncate text-[12.5px] font-medium text-[var(--text-secondary)]">{displayName}</span>
          </div>
        )}

        {isScoped && (
          <button
            onClick={onChangePassword}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--text-secondary)]"
          >
            <KeyRound size={15} className="shrink-0" />
            Change password
          </button>
        )}

        <button
          onClick={onLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--text-secondary)]"
        >
          <LogOut size={15} className="shrink-0" />
          Sign out
        </button>
      </div>
    </div>
  )
}

// ── Main shell ────────────────────────────────────────────────────────────────
export default function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const { logout, displayName, allowedPages, changePassword, error } = useAuthStore()
  const isScoped = getSubdomainSlug() !== null

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [showPwModal, setShowPwModal] = useState(false)
  const [pwCurrent, setPwCurrent] = useState('')
  const [pwNew, setPwNew] = useState('')
  const [pwConfirm, setPwConfirm] = useState('')
  const [pwLoading, setPwLoading] = useState(false)
  const [pwSuccess, setPwSuccess] = useState(false)
  const [pwError, setPwError] = useState('')

  // Close drawer on navigation
  useEffect(() => { setDrawerOpen(false) }, [location.pathname])

  // Lock body scroll when drawer is open
  useEffect(() => {
    if (drawerOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [drawerOpen])

  const visibleItems = (isScoped
    ? NAV_ITEMS.filter((item) => allowedPages.includes(item.id))
    : [...NAV_ITEMS]) as typeof NAV_ITEMS[number][]

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  const handleChangePassword = async () => {
    setPwError('')
    if (pwNew !== pwConfirm) { setPwError('Passwords do not match'); return }
    if (pwNew.length < 6) { setPwError('Must be at least 6 characters'); return }
    setPwLoading(true)
    const ok = await changePassword(pwCurrent, pwNew)
    setPwLoading(false)
    if (ok) {
      setPwSuccess(true)
      setTimeout(() => {
        setShowPwModal(false); setPwSuccess(false)
        setPwCurrent(''); setPwNew(''); setPwConfirm('')
      }, 1400)
    } else {
      setPwError(error || 'Failed to change password')
    }
  }

  const currentPageLabel = visibleItems.find((item) =>
    item.to === location.pathname ||
    (item.to !== '/' && location.pathname.startsWith(item.to))
  )?.label ?? 'Digital DNA'

  return (
    <div className="flex min-h-screen bg-[var(--page-bg)]">
      {/* ── Desktop sidebar ── */}
      <aside
        className="hidden lg:flex fixed inset-y-0 left-0 z-30 flex-col border-r border-[var(--border-1)] bg-[var(--surface-1)]"
        style={{ width: 'var(--sidebar-width)' }}
      >
        <SidebarContent
          visibleItems={visibleItems}
          isScoped={isScoped}
          displayName={displayName}
          onLogout={handleLogout}
          onChangePassword={() => setShowPwModal(true)}
        />
      </aside>

      {/* ── Mobile header ── */}
      <header
        className="lg:hidden fixed inset-x-0 top-0 z-40 flex items-center justify-between border-b border-[var(--border-1)] bg-[var(--surface-1)] px-4"
        style={{ height: 'var(--header-height)' }}
      >
        <button
          onClick={() => setDrawerOpen(true)}
          className="flex h-9 w-9 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)]"
          aria-label="Open navigation"
        >
          <Menu size={20} />
        </button>

        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-white">
            <span className="font-[var(--font-display)] text-[10px] font-bold text-black">DD</span>
          </div>
          <span className="font-[var(--font-display)] text-[13.5px] font-semibold text-[var(--text-primary)]">
            {currentPageLabel}
          </span>
        </div>

        {/* Spacer */}
        <div className="w-9" />
      </header>

      {/* ── Mobile drawer ── */}
      <div
        className={clsx(
          'lg:hidden fixed inset-0 z-50 transition-all duration-200',
          drawerOpen ? 'pointer-events-auto' : 'pointer-events-none',
        )}
      >
        {/* Backdrop */}
        <div
          className={clsx(
            'absolute inset-0 bg-black/70 backdrop-blur-sm transition-opacity duration-200',
            drawerOpen ? 'opacity-100' : 'opacity-0',
          )}
          onClick={() => setDrawerOpen(false)}
        />
        {/* Drawer panel */}
        <aside
          className={clsx(
            'absolute inset-y-0 left-0 flex w-[260px] flex-col border-r border-[var(--border-1)] bg-[var(--surface-1)] shadow-[var(--shadow-overlay)] transition-transform duration-200',
            drawerOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <SidebarContent
            visibleItems={visibleItems}
            isScoped={isScoped}
            displayName={displayName}
            onLogout={handleLogout}
            onChangePassword={() => { setShowPwModal(true); setDrawerOpen(false) }}
            onClose={() => setDrawerOpen(false)}
          />
        </aside>
      </div>

      {/* ── Main content ── */}
      <main className="flex min-h-screen flex-1 flex-col lg:pl-[220px]">
        {/* Mobile top spacer */}
        <div className="lg:hidden" style={{ height: 'var(--header-height)' }} />

        {/* Page content */}
        <div className="flex-1 p-4 sm:p-5 lg:p-7">
          <Outlet />
        </div>
      </main>

      {/* ── Change Password Modal ── */}
      {showPwModal && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => { setShowPwModal(false); setPwError('') }}
          />
          <div className="relative w-full max-w-sm animate-scale-in rounded-2xl border border-[var(--border-1)] bg-[var(--surface-2)] p-6 shadow-[var(--shadow-overlay)]">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="font-[var(--font-display)] text-[15px] font-semibold text-[var(--text-primary)]">
                Change Password
              </h2>
              <button
                onClick={() => { setShowPwModal(false); setPwError(''); setPwSuccess(false) }}
                className="flex h-7 w-7 items-center justify-center rounded-lg text-[var(--text-muted)] hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)] transition-colors"
              >
                <X size={15} />
              </button>
            </div>

            {pwSuccess ? (
              <div className="flex flex-col items-center gap-3 py-6 text-center">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--success-dim)]">
                  <span className="text-xl">✓</span>
                </div>
                <p className="text-[13px] text-[var(--success)]">Password changed!</p>
              </div>
            ) : (
              <div className="space-y-3">
                {(['Current password', 'New password', 'Confirm new password'] as const).map((label, i) => (
                  <div key={label}>
                    <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-[var(--text-muted)]">
                      {label}
                    </label>
                    <input
                      type="password"
                      placeholder={i === 0 ? '••••••' : i === 1 ? 'Min. 6 characters' : ''}
                      value={[pwCurrent, pwNew, pwConfirm][i]}
                      onChange={(e) => [setPwCurrent, setPwNew, setPwConfirm][i](e.target.value)}
                      className="field"
                      autoFocus={i === 0}
                    />
                  </div>
                ))}
                {pwError && (
                  <p className="rounded-lg bg-[var(--error-dim)] px-3 py-2 text-[12px] text-[var(--error)]">
                    {pwError}
                  </p>
                )}
                <button
                  onClick={handleChangePassword}
                  disabled={pwLoading || !pwCurrent || !pwNew || !pwConfirm}
                  className="mt-1 flex w-full items-center justify-center gap-2 rounded-xl bg-white px-4 py-2.5 text-[13px] font-semibold text-black transition-all hover:bg-white/90 disabled:opacity-40"
                >
                  {pwLoading && <Loader2 size={14} className="animate-spin" />}
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
