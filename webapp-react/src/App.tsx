import { Routes, Route } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import RequireAuth from './components/auth/RequireAuth'
import LoginPage from './pages/LoginPage'
import AdminLoginPage from './pages/AdminLoginPage'
import AdminPage from './pages/AdminPage'
import DashboardPage from './pages/DashboardPage'
import GeneratePage from './pages/GeneratePage'
import GraphPage from './pages/GraphPage'
import CoveragePage from './pages/CoveragePage'
import WorkflowPage from './pages/WorkflowPage'
import HistoryPage from './pages/HistoryPage'
import ConfigPage from './pages/ConfigPage'
import CustomizePage from './pages/CustomizePage'
import LandingPage from './pages/LandingPage'
import FounderPackPage from './pages/FounderPackPage'
import { isApexDomain } from './utils/subdomain'

export default function App() {
  if (isApexDomain()) {
    return <LandingPage />
  }

  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/admin/login" element={<AdminLoginPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/admin/founders/:slug" element={<FounderPackPage />} />

      {/* Protected founder routes */}
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="generate" element={<GeneratePage />} />
          <Route path="customize" element={<CustomizePage />} />
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
