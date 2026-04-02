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
      <header className="flex items-center justify-between border-b border-gray-800 px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500" />
          <h1 className="text-lg font-bold tracking-tight">Digital DNA</h1>
        </div>
        <FounderSelector />
      </header>

      {/* Nav */}
      <nav className="flex gap-1 border-b border-gray-800 px-6">
        {NAV_ITEMS.map(({ to, label, icon: Icon, ...rest }) => (
          <NavLink
            key={to}
            to={to}
            end={'end' in rest}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'border-indigo-500 text-indigo-400'
                  : 'border-transparent text-gray-400 hover:text-gray-200',
              )
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Content */}
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
