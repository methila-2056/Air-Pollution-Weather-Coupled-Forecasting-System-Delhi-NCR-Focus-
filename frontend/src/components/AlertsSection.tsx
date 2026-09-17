import { AlertTriangle, Scale } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Alert, GrapAssessment } from '../types'
import { readableOnHex } from '../lib/aqi'
import AlertList from './AlertList'
import EmptyState from './EmptyState'

interface Props {
  alerts: Alert[]
  grap: GrapAssessment | null
  limit?: number
}

export default function AlertsSection({ alerts, grap, limit = 3 }: Props) {
  return (
    <section className="card">
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden="true" />
          <h2 className="text-base font-bold text-slate-900">Alerts & warnings</h2>
        </div>
        <Link to="/alerts" className="text-xs font-semibold text-inst-700 hover:underline">
          Open alert centre →
        </Link>
      </div>

      {grap && (
        <div className="mb-4 flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
          <Scale className="h-5 w-5 shrink-0 text-inst-700" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full px-3 py-0.5 text-xs font-bold" style={{ backgroundColor: grap.color, color: readableOnHex(grap.color) }}>
                {grap.title}
              </span>
              <span className="text-xs text-slate-600">
                {grap.status === 'ACTIVE' ? 'operative' : 'not invoked'} · NCR avg AQI {grap.aqi ?? '--'}
              </span>
            </div>
            <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-600">{grap.advisory}</p>
          </div>
        </div>
      )}

      {alerts.length ? (
        <AlertList alerts={alerts.slice(0, limit)} />
      ) : (
        <EmptyState title="No active alerts" hint="No warning thresholds are currently exceeded for the network." />
      )}
    </section>
  )
}