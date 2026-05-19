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
import AskRevSurePage from './pages/AskRevSurePage'
import ChatPage from './pages/ChatPage'
import ContentStudioPage from './pages/ContentStudioPage'
import AskSharathAdminPage from './pages/AskSharathAdminPage'
import SubdomainAuthAdminPage from './pages/SubdomainAuthAdminPage'
import SubdomainGate from './components/SubdomainGate'
import { isApexDomain, getSubdomainSlug } from './utils/subdomain'
import { Loader2 } from 'lucide-react'

const OsApp = lazy(() => import('./pages/os/OsApp'))

export default function App() {
  const slug = getSubdomainSlug()

  // OS management interface at os.tagent.club
  if (slug === 'os') {
    return (
      <Suspense fallback={<div className="flex h-screen items-center justify-center bg-black"><Loader2 size={20} className="animate-spin text-white/30" /></div>}>
        <Routes>
          <Route path="/admin/login" element={<AdminLoginPage />} />
          <Route path="*" element={<OsApp />} />
        </Routes>
      </Suspense>
    )
  }

  // Show the company landing page at tagent.club (apex domain)
  if (isApexDomain() && window.location.pathname === '/') {
    return <LandingPage />
  }

  // AskSharath — public chatbot ONLY on asksharath.tagent.club (now gated)
  if (slug === 'asksharath') {
    return (
      <Routes>
        {/* Public — wrapped in SubdomainGate so the backend's password gate
            shows in the UI when enabled. */}
        <Route index element={<SubdomainGate brandLabel="Ask Sharath"><AskSharathPage /></SubdomainGate>} />
        <Route path="chat" element={<SubdomainGate brandLabel="Ask Sharath"><ChatPage /></SubdomainGate>} />
        <Route path="login" element={<LoginPage />} />
        <Route path="admin/login" element={<AdminLoginPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="admin/asksharath" element={<AskSharathAdminPage />} />
        <Route path="admin/subdomain-auth" element={<SubdomainAuthAdminPage />} />
        <Route path="admin/founders/:slug" element={<FounderPackPage />} />
        {/* Auth-protected founder tools */}
        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="generate" element={<GeneratePage />} />
            <Route path="content-studio" element={<ContentStudioPage />} />
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

  // AskRevSure — public Q&A + journey dashboard at askrevsure.tagent.club
  if (slug === 'askrevsure') {
    return (
      <Routes>
        <Route index element={<SubdomainGate brandLabel="Ask RevSure"><AskRevSurePage /></SubdomainGate>} />
        <Route path="login" element={<LoginPage />} />
        <Route path="admin/login" element={<AdminLoginPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="admin/subdomain-auth" element={<SubdomainAuthAdminPage />} />
        <Route path="admin/asksharath" element={<AskSharathAdminPage />} />
        <Route path="admin/founders/:slug" element={<FounderPackPage />} />
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
      <Route path="/admin/subdomain-auth" element={<SubdomainAuthAdminPage />} />
      <Route path="/admin/founders/:slug" element={<FounderPackPage />} />

      {/* Protected founder routes */}
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="generate" element={<GeneratePage />} />
          <Route path="content-studio" element={<ContentStudioPage />} />
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
