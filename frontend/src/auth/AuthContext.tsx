import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  clearSession,
  getMe,
  getStoredToken,
  getStoredUser,
  isTransientStatus,
  login as apiLogin,
  logout as apiLogout,
  storeSession,
} from '../api/client'
import type { AuthUser } from '../types'

interface AuthContextValue {
  user: AuthUser | null
  token: string | null
  loading: boolean
  login: (email: string, password: string) => Promise<AuthUser>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser())
  const [token, setToken] = useState<string | null>(() => getStoredToken())
  // Render from the stored session immediately instead of blocking every
  // protected page on GET /api/auth/me. The hosted Postgres can take seconds
  // to resume, and gating the whole UI on that round-trip left the Tools pages
  // stuck on "Verifying session…". The token is still revalidated in the
  // background (below) and the session is cleared if it is rejected.
  const [loading, setLoading] = useState<boolean>(false)

  useEffect(() => {
    let cancelled = false
    const token = getStoredToken()
    if (!token) {
      setLoading(false)
      return
    }
    getMe()
      .then((res) => {
        if (cancelled) return
        setUser(res.data)
        setToken(token)
        sessionStorage.setItem('aerocast_user', JSON.stringify(res.data))
      })
      .catch((err) => {
        if (cancelled) return
        // Render free-tier back-ends sleep after idle; a gateway 502/503/429
        // while waking means the token is still valid — keep the stored
        // session so panels can retry instead of logging the analyst out
        // mid-demo. A 429 was previously read as "session rejected", which is
        // how a rate-limited wake turned into a spurious logout.
        const status = err?.response?.status
        if (isTransientStatus(status)) return
        clearSession()
        setUser(null)
        setToken(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const res = await apiLogin(email, password)
    storeSession(res.data.access_token, res.data.user)
    setToken(res.data.access_token)
    setUser(res.data.user)
    return res.data.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await apiLogout()
    } catch {
      // Token may already be invalid — clear locally regardless.
    }
    clearSession()
    setUser(null)
    setToken(null)
  }, [])

  const value = useMemo(
    () => ({ user, token, loading, login, logout }),
    [user, token, loading, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}