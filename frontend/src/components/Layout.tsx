import { ReactNode, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  Cloud,
  CloudSun,
  Flame,
  Gauge,
  LayoutDashboard,
  LogOut,
  Map as MapIcon,
  Menu,
  User as UserIcon,
  Wind,
  X,
} from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import SystemStatus from './SystemStatus'

const primaryNav = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { to: '/forecast', label: '72H Forecast', icon: Gauge },
  { to: '/atmosphere', label: 'Atmosphere', icon: CloudSun },
  { to: '/fire-plume', label: 'Transport', icon: Flame },
  { to: '/map', label: 'NCR Map', icon: MapIcon },
  { to: '/alerts', label: 'Alerts', icon: AlertTriangle },
]

const tools = [
  { to: '/overview', label: 'Operational Overview' },
  { to: '/explanation', label: 'Forecast Explainability' },
  { to: '/model-performance', label: 'Model Performance' },
  { to: '/spatial', label: 'Spatial AQ Outlook' },
  { to: '/data', label: 'Data & System Sources' },
]

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
}

function UserMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  async function handleLogout() {
    setOpen(false)
    await logout()
    navigate('/login', { replace: true })
  }

  if (!user) return null

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-white transition-colors hover:bg-white/10"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-sky-700 text-sm font-bold text-white">
          {initials(user.name)}
        </span>
        <span className="hidden text-left md:block">
          <span className="block text-sm font-semibold leading-tight">{user.name}</span>
          <span className="block text-[11px] leading-tight text-blue-200">{user.role}</span>
        </span>
        <ChevronDown className="h-4 w-4 text-blue-200" aria-hidden="true" />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-2 w-56 rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
        >
          <div className="border-b border-slate-100 px-4 py-2">
            <p className="truncate text-sm font-semibold text-slate-900">{user.name}</p>
            <p className="truncate text-xs text-slate-500">{user.email}</p>
          </div>
          <NavLink
            to="/profile"
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 ${isActive ? 'bg-slate-50 font-semibold' : ''}`
            }
          >
            <UserIcon className="h-4 w-4 text-slate-400" aria-hidden="true" /> My profile
          </NavLink>
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}

function ToolsMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="nav-link items-center"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Wind className="h-4 w-4" aria-hidden="true" /> Tools
        <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute left-0 top-full z-40 mt-1 w-60 rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
        >
          {tools.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `block px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 ${isActive ? 'bg-slate-50 font-semibold text-inst-800' : ''}`
              }
            >
              {t.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Layout({ children }: { children?: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="flex min-h-screen flex-col">
      {/* ---------- National header ---------- */}
      <header className="bg-inst-800 text-white">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/10">
            <Activity className="h-6 w-6 text-cyan-300" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-bold uppercase tracking-wide sm:text-base">AeroCast-NCR</p>
            <p className="hidden truncate text-xs text-blue-200 sm:block">
              National Air Quality Forecasting Unit · Delhi NCR
            </p>
          </div>

          <button
            type="button"
            onClick={() => setMobileOpen((v) => !v)}
            className="ml-auto rounded-lg p-2 text-white hover:bg-white/10 md:hidden"
            aria-label="Toggle navigation menu"
            aria-expanded={mobileOpen}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>

          <span className="ml-auto hidden rounded-full border border-blue-300/40 px-3 py-1 text-xs text-blue-100 xl:inline-block">
            SIH 2026 · PS SIH26082
          </span>
          <SystemStatus className="ml-auto lg:ml-0 xl:ml-3" />
          <div className="lg:ml-1">
            <UserMenu />
          </div>
        </div>
      </header>

      {/* ---------- Secondary navigation ---------- */}
      <nav className="sticky top-0 z-30 border-b border-slate-200 bg-white" aria-label="Primary">
        <div className="mx-auto hidden max-w-7xl items-center gap-1 px-6 md:flex">
          {primaryNav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link ${isActive ? 'nav-link-active' : ''}`}
            >
              <item.icon className="h-4 w-4" aria-hidden="true" /> {item.label}
            </NavLink>
          ))}
          <ToolsMenu />
        </div>

        {mobileOpen && (
          <div className="border-t border-slate-200 bg-white md:hidden">
            <div className="mx-auto max-w-7xl space-y-1 px-4 py-3">
              {primaryNav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  onClick={() => setMobileOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${
                      isActive ? 'bg-inst-50 text-inst-800' : 'text-slate-700 hover:bg-slate-50'
                    }`
                  }
                >
                  <item.icon className="h-4 w-4" aria-hidden="true" /> {item.label}
                </NavLink>
              ))}
              <p className="px-3 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Tools</p>
              {tools.map((t) => (
                <NavLink
                  key={t.to}
                  to={t.to}
                  onClick={() => setMobileOpen(false)}
                  className={({ isActive }) =>
                    `block rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-inst-50 font-semibold text-inst-800' : 'text-slate-700 hover:bg-slate-50'}`
                  }
                >
                  {t.label}
                </NavLink>
              ))}
              <NavLink
                to="/profile"
                onClick={() => setMobileOpen(false)}
                className="block rounded-lg px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                My profile
              </NavLink>
            </div>
          </div>
        )}
      </nav>

      {/* ---------- Content ---------- */}
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
        {children ?? <Outlet />}
      </main>

      {/* ---------- Footer ---------- */}
      <footer className="mt-8 border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl space-y-2 px-6 py-6">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-500">
            <span className="flex items-center gap-1.5">
              <Cloud className="h-3.5 w-3.5 text-inst-600" aria-hidden="true" /> AeroCast-NCR · SIH26082
            </span>
            <span>Data sources: CPCB · NASA FIRMS · Open-Meteo · IMD</span>
            <span>NavIC-assisted aerosol verification</span>
          </div>
          <p className="text-xs leading-relaxed text-slate-500">
            Prototype developed for Smart India Hackathon 2026 — SIH26082. Not an official Government of India service.
          </p>
        </div>
      </footer>
    </div>
  )
}