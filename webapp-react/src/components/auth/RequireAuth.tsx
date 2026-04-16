import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuthStore } from '../../store/useAuthStore'
import { getSubdomainSlug } from '../../utils/subdomain'

// Map URL paths to page IDs used in permissions
const PATH_TO_PAGE: Record<string, string> = {
  '/': 'dashboard',
  '/generate': 'generate',
  '/customize': 'customize',
  '/graph': 'graph',
  '/coverage': 'coverage',
  '/workflow': 'workflow',
  '/history': 'history',
  '/config': 'config',
}

export default function RequireAuth() {
  const { status, bootstrap, allowedPages } = useAuthStore()
  const location = useLocation()
  const isScoped = getSubdomainSlug() !== null

  useEffect(() => {
    if (status === 'unknown') {
      bootstrap()
    }
  }, [status, bootstrap])

  if (status === 'unknown') {
    return (
      <div className="flex h-screen items-center justify-center bg-black">
        <Loader2 size={20} className="animate-spin text-white" />
      </div>
    )
  }

  if (status === 'anon') {
    return <Navigate to="/login" replace />
  }

  // Check if current page is allowed (only for scoped sessions)
  if (isScoped && allowedPages.length > 0) {
    const currentPage = PATH_TO_PAGE[location.pathname] || ''
    if (currentPage && !allowedPages.includes(currentPage)) {
      // Redirect to first allowed page
      const firstAllowed = Object.entries(PATH_TO_PAGE).find(
        ([, pageId]) => allowedPages.includes(pageId)
      )
      if (firstAllowed) {
        return <Navigate to={firstAllowed[0]} replace />
      }
    }
  }

  return <Outlet />
}
