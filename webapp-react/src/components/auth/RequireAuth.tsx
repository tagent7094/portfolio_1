import { useEffect } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuthStore } from '../../store/useAuthStore'

export default function RequireAuth() {
  const { status, bootstrap } = useAuthStore()

  useEffect(() => {
    if (status === 'unknown') {
      bootstrap()
    }
  }, [status, bootstrap])

  if (status === 'unknown') {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-950">
        <Loader2 size={20} className="animate-spin text-white" />
      </div>
    )
  }

  if (status === 'anon') {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
