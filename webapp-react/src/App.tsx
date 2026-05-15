import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import RequireAuth from './components/auth/RequireAuth'
import LoginPage from './pages/LoginPage'
import AdminLoginPage from './pages/AdminLoginPage'
import AdminPage from './pages/AdminPage'
import DashboardPage from './pages/DashboardPage'
import GraphPage from './pages/GraphPage'
import CoveragePage from './pages/CoveragePage'
import WorkflowPage from './pages/WorkflowPage'
import HistoryPage from './pages/HistoryPage'
import ConfigPage from './pages/ConfigPage'
import GeneratePage from './pages/GeneratePage'
import LandingPage from './pages/LandingPage'
import FounderPackPage from './pages/FounderPackPage'
import AskSharathPage from './pages/AskSharathPage'
import ChatPage from './pages/ChatPage'
import AskSharathAdminPage from './pages/AskSharathAdminPage'
import { isApexDomain, getSubdomainSlug } from './utils/subdomain'
import { Loader2 } from 'lucide-react'

const OsApp = lazy(() => import('./pages/os/OsApp'))

export default function App() {
  const slug = getSubdomainSlug()

  // OS management interface at os.tagent.club
  if (slug === 'os') {
    return (
      <Suspense fallback={<div className="flex h-screen items-center justify-center bg-black"><Loader2 size={20} className="animate-spin text-white/30" /></div>}>
        <OsApp />
      </Suspense>
    )
  }

  // Show the company landing page at tagent.club (apex domain)
  if (isApexDomain() && window.location.pathname === '/') {
    return <LandingPage />
  }

  // AskSharath — public chatbot ONLY on asksharath.tagent.club
  if (slug === 'asksharath') {
    return (
      <Routes>
        {/* Public — no auth required */}
        <Route index element={<AskSharathPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="admin/login" element={<AdminLoginPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="admin/asksharath" element={<AskSharathAdminPage />} />
        <Route path="admin/founders/:slug" element={<FounderPackPage />} />
        {/* Auth-protected founder tools */}
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="generate" element={<GeneratePage />} />
            <Route path="graph" element={<GraphPage />} />
            <Route path="coverage" element={<CoveragePage />} />
            <Route path="workflow" element={<WorkflowPage />} />
            <Route path="history" element={<HistoryPage />} />
            <Route path="config" element={<ConfigPage />} />
          </Route>
        </Route>
      </Routes>
    )
  }

  // All other subdomains + localhost — standard founder app
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/admin/login" element={<AdminLoginPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/admin/asksharath" element={<AskSharathAdminPage />} />
      <Route path="/admin/founders/:slug" element={<FounderPackPage />} />

      {/* Protected founder routes */}
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="generate" element={<GeneratePage />} />
          <Route path="graph" element={<GraphPage />} />
          <Route path="coverage" element={<CoveragePage />} />
          <Route path="workflow" element={<WorkflowPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="config" element={<ConfigPage />} />
        </Route>
      </Route>
    </Routes>
  )
}
