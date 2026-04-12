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
} from 'lucide-react'
import FounderSelector from './FounderSelector'
import clsx from 'clsx'
import { useAuthStore } from '../../store/useAuthStore'
import { getSubdomainSlug } from '../../utils/subdomain'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/generate', label: 'Generate', icon: Sparkles },
  { to: '/customize', label: 'Customize', icon: Wand2 },
  { to: '/graph', label: 'Graph', icon: GitFork },
  { to: '/coverage', label: 'Coverage', icon: BarChart3 },
  { to: '/workflow', label: 'Workflow', icon: Workflow },
  { to: '/history', label: 'History', icon: Clock },
  { to: '/config', label: 'Config', icon: Settings },
] as const

export default function AppShell() {
  const navigate = useNavigate()
  const { logout, displayName } = useAuthStore()
  const isScoped = getSubdomainSlug() !== null

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

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

        <div className="flex items-center gap-3">
          {!isScoped && <FounderSelector />}
          {isScoped && (
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[12px] font-medium text-white/80 transition-colors hover:bg-white/10 hover:text-white"
              title="Sign out"
            >
              <LogOut size={13} />
              Sign out
            </button>
          )}
        </div>
      </header>

      {/* Nav */}
      <nav className="flex gap-0.5 border-b border-white/10 px-5">
        {NAV_ITEMS.map(({ to, label, icon: Icon, ...rest }) => (
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
    </div>
  )
}
