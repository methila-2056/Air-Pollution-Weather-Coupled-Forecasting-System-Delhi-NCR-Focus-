import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './AuthContext'

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, token, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center" aria-busy="true">
        <div className="flex flex-col items-center gap-3 text-gray-500">
          <span className="h-8 w-8 animate-spin rounded-full border-4 border-blue-100 border-t-blue-700" />
          <span className="text-sm">Verifying session…</span>
        </div>
      </div>
    )
  }

  if (!user || !token) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }

  return <>{children}</>
}