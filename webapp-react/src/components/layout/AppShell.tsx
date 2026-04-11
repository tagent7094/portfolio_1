import { Outlet, NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Sparkles,
  Wand2,
  GitFork,
  BarChart3,
  Workflow,
  Clock,
  Settings,
} from 'lucide-react'
import FounderSelector from './FounderSelector'
import clsx from 'clsx'

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
  return (
    <div className="flex h-screen flex-col bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="relative flex items-center justify-between border-b border-white/[0.04] px-6 py-3">
        {/* Subtle top glow */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-indigo-500/20 to-transparent" />

        <div className="flex items-center gap-3.5">
          <div className="relative h-8 w-8">
            <div className="absolute inset-0 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 opacity-80 blur-[6px]" />
            <div className="relative h-8 w-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-500/20" />
          </div>
          <div>
            <h1 className="font-[var(--font-display)] text-[15px] font-semibold tracking-tight text-gray-100">
              Digital DNA
            </h1>
          </div>
        </div>

        <FounderSelector />
      </header>

      {/* Nav */}
      <nav className="flex gap-0.5 border-b border-white/[0.04] px-5">
        {NAV_ITEMS.map(({ to, label, icon: Icon, ...rest }) => (
          <NavLink
            key={to}
            to={to}
            end={'end' in rest}
            className={({ isActive }) =>
              clsx(
                'relative flex items-center gap-2 px-3.5 py-2.5 text-[13px] font-medium transition-all duration-200',
                isActive
                  ? 'text-gray-100'
                  : 'text-gray-500 hover:text-gray-300',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={15} className={isActive ? 'text-indigo-400' : ''} />
                {label}
                {isActive && (
                  <span className="absolute inset-x-2 -bottom-px h-[2px] rounded-full bg-gradient-to-r from-indigo-500 to-violet-500" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Content */}
      <main className="relative flex-1 overflow-auto p-5">
        <Outlet />
      </main>
    </div>
  )
}
