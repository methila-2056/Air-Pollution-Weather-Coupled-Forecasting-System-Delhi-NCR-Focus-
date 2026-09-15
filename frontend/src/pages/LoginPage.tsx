import { FormEvent, useEffect, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Activity, AlertCircle, Eye, EyeOff, LockKeyhole, Mail } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { getDemoCredentials } from '../api/client'
import type { DemoCredentials } from '../types'

export default function LoginPage() {
  const { user, token, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  const next = params.get('next')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [demo, setDemo] = useState<DemoCredentials | null>(null)

  useEffect(() => {
    getDemoCredentials()
      .then((res) => setDemo(res.data))
      .catch(() => setDemo(null))
  }, [])

  if (user && token) {
    return <Navigate to={next && !next.startsWith('/login') ? next : '/dashboard'} replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email.trim(), password)
      navigate(next && !next.startsWith('/login') ? next : '/dashboard', { replace: true })
    } catch {
      setError('Invalid email or password. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  function fillDemo() {
    if (!demo) return
    setEmail(demo.email)
    setPassword(demo.password)
    setError(null)
  }

  return (
    <div className="flex min-h-screen flex-col bg-blue-50/60">
      <header className="border-b border-blue-900/20 bg-blue-900 text-white">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-6 py-4">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/10">
            <Activity className="h-6 w-6 text-cyan-300" aria-hidden="true" />
          </span>
          <div>
            <p className="text-sm font-bold leading-tight uppercase tracking-wide">AeroCast-NCR</p>
            <p className="text-xs text-blue-200">National Air Quality Forecasting · Delhi NCR</p>
          </div>
          <span className="ml-auto hidden rounded-full border border-blue-300/40 px-3 py-1 text-xs text-blue-100 sm:inline-block">
            SIH 2026 · PS SIH26082
          </span>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 bg-slate-50 px-8 py-6 text-center">
              <h1 className="text-xl font-bold text-slate-900">Analyst Sign In</h1>
              <p className="mt-1 text-sm text-slate-500">
                Restricted access for authorised air-quality analysts
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5 px-8 py-7" aria-label="Sign in">
              <div>
                <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-slate-700">
                  Email address
                </label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                  <input
                    id="email"
                    type="email"
                    autoComplete="username"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="analyst@aerocast.in"
                    className="w-full rounded-lg border border-slate-300 bg-white py-2.5 pl-10 pr-3 text-sm text-slate-900 outline-none ring-blue-600/30 focus:border-blue-500 focus:ring-2"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-slate-700">
                  Password
                </label>
                <div className="relative">
                  <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full rounded-lg border border-slate-300 bg-white py-2.5 pl-10 pr-10 text-sm text-slate-900 outline-none ring-blue-600/30 focus:border-blue-500 focus:ring-2"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:text-slate-600"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {error && (
                <div
                  role="alert"
                  className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700"
                >
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{error}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-lg bg-blue-800 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          </div>

          {demo && (
            <div className="mt-4 rounded-xl border border-blue-100 bg-blue-50 px-6 py-4">
              <p className="text-sm font-semibold text-blue-900">Hackathon demo access</p>
              <p className="mt-1 break-all text-xs leading-relaxed text-blue-800">
                Email: <span className="font-mono">{demo.email}</span>&nbsp;· Password:{' '}
                <span className="font-mono">{demo.password}</span>
              </p>
              <button
                type="button"
                onClick={fillDemo}
                className="mt-2 rounded-lg border border-blue-700 bg-white px-3 py-1.5 text-xs font-semibold text-blue-800 transition-colors hover:bg-blue-100"
              >
                Autofill demo credentials
              </button>
            </div>
          )}

          <p className="mt-6 text-center text-xs leading-relaxed text-slate-500">
            Prototype developed for Smart India Hackathon 2026 — SIH26082.
            <br />
            Not an official Government of India service.
          </p>
        </div>
      </main>
    </div>
  )
}