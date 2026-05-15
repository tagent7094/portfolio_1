import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Loader2 } from 'lucide-react'
import OsLayout from './OsLayout'

export default function OsApp() {
  const [status, setStatus] = useState<'checking' | 'authed' | 'denied'>('checking')

  useEffect(() => {
    const check = async () => {
      try {
        await apiGet('/api/os/stats')
        setStatus('authed')
      } catch {
        setStatus('denied')
      }
    }
    check()
  }, [])

  if (status === 'checking') {
    return (
      <div className="flex h-screen items-center justify-center bg-black">
        <Loader2 size={20} className="animate-spin text-white/30" />
      </div>
    )
  }

  if (status === 'denied') {
    window.location.assign('/admin/login')
    return null
  }

  return <OsLayout />
}
