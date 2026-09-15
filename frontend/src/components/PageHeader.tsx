import { ChevronRight, Clock } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { tsFmt } from '../lib/aqi'

interface Breadcrumb {
  label: string
  to?: string
}

interface PageHeaderProps {
  title: string
  subtitle?: string
  breadcrumbs?: Breadcrumb[]
  lastUpdated?: string | null | undefined
  actions?: ReactNode
}

export default function PageHeader({ title, subtitle, breadcrumbs, lastUpdated, actions }: PageHeaderProps) {
  return (
    <div className="mb-6">
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className="mb-2 flex items-center gap-1 text-xs text-slate-500" aria-label="Breadcrumb">
          {breadcrumbs.map((b, i) => (
            <span key={b.label} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="h-3 w-3 text-slate-300" aria-hidden="true" />}
              {b.to ? (
                <Link to={b.to} className="hover:text-inst-700">
                  {b.label}
                </Link>
              ) : (
                <span className="font-medium text-slate-700">{b.label}</span>
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-500">
              <Clock className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" /> Updated {tsFmt(lastUpdated)} UTC
            </span>
          )}
          {actions}
        </div>
      </div>
    </div>
  )
}