import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, TrendingDown, TrendingUp, Activity } from 'lucide-react'
import { getEvents, getStations } from '../api/client'
import PageHeader from '../components/PageHeader'
import LoadingState from '../components/LoadingState'
import ErrorState from '../components/ErrorState'
import EmptyState from '../components/EmptyState'
import { fmt, tsFmt } from '../lib/aqi'
import type { PollutionEventsCurrent, PollutionEvent, Station } from '../types'

const eventMeta: Record<string, { label: string; icon: typeof TrendingUp; color: string }> = {
  pollution_surge: { label: 'Pollution surge', icon: TrendingUp, color: 'text-orange-700 bg-orange-50 border-orange-300' },
  pollution_relief: { label: 'Pollution relief', icon: TrendingDown, color: 'text-green-700 bg-green-50 border-green-300' },
  high_risk_episode: { label: 'High-risk episode', icon: AlertTriangle, color: 'text-red-700 bg-red-50 border-red-300' },
}

const confidenceStyle: Record<string, string> = {
  high: 'bg-green-100 text-green-800',
  medium: 'bg-amber-100 text-amber-800',
  low: 'bg-red-100 text-red-800',
}

function EventCard({ ev }: { ev: PollutionEvent }) {
  const meta = eventMeta[ev.event_type] ?? { label: ev.event_type, icon: Activity, color: 'text-slate-700 bg-slate-50 border-slate-300' }
  const Icon = meta.icon
  const conf = ev.confidence
  return (
    <div className={`card border ${meta.color}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-start gap-3">
          <Icon className="mt-0.5 flex-shrink-0" size={20} />
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-bold text-slate-900">{meta.label}</p>
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${ev.status === 'active' ? 'bg-red-100 text-red-800' : 'bg-slate-100 text-slate-700'}`}>
                {ev.status}
              </span>
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${confidenceStyle[conf.label] ?? 'bg-slate-100 text-slate-700'}`}>
                confidence: {conf.label}
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Window {tsFmt(ev.start_time)} → {ev.end_time ? tsFmt(ev.end_time) : 'ongoing'}
            </p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-xs text-slate-500">Severity</p>
          <p className="text-sm font-bold capitalize text-slate-900">{ev.severity}</p>
        </div>
      </div>

      <p className="mt-2 text-sm leading-relaxed text-slate-700">{ev.severity_label}</p>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {ev.expected_peak != null && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Expected peak</p>
            <p className="text-base font-bold tabular-nums text-slate-900">{fmt(ev.expected_peak, 0)} μg/m³</p>
            <p className="text-xs text-slate-500">{ev.expected_peak_time ? tsFmt(ev.expected_peak_time) : '—'}</p>
          </div>
        )}
        {ev.expected_trough != null && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Expected trough</p>
            <p className="text-base font-bold tabular-nums text-slate-900">{fmt(ev.expected_trough, 0)} μg/m³</p>
            <p className="text-xs text-slate-500">{ev.expected_trough_time ? tsFmt(ev.expected_trough_time) : '—'}</p>
          </div>
        )}
        {conf.lower_bound_ugm3 != null && conf.upper_bound_ugm3 != null && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Prediction interval</p>
            <p className="text-base font-bold tabular-nums text-slate-900">
              {fmt(conf.lower_bound_ugm3, 0)}–{fmt(conf.upper_bound_ugm3, 0)} μg/m³
            </p>
            <p className="text-xs text-slate-500">{conf.coverage_target != null ? `${(conf.coverage_target * 100).toFixed(0)}% coverage` : ''}</p>
          </div>
        )}
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
          <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Model basis</p>
          <p className="text-sm font-semibold leading-tight text-slate-900">{conf.basis}</p>
          {conf.test_r2 != null && <p className="text-xs text-slate-500">test R² {fmt(conf.test_r2, 2)}</p>}
        </div>
      </div>

      {ev.contributing_factors.length > 0 && (
        <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <p className="mb-2 text-[10px] font-medium uppercase tracking-wide text-slate-500">Contributing factors (from stored data)</p>
          <ul className="space-y-1.5">
            {ev.contributing_factors.map((f, i) => (
              <li key={i} className="flex flex-wrap items-center gap-x-2 text-sm text-slate-700">
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                    f.status === 'active' || f.status === 'triggering' || f.status === 'supporting'
                      ? 'bg-red-100 text-red-800'
                      : 'bg-slate-200 text-slate-600'
                  }`}
                >
                  {f.status}
                </span>
                <span className="font-medium">{f.factor}</span>
                {f.value != null && <span className="tabular-nums text-slate-600">{fmt(f.value, 1)}</span>}
                {f.description && <span className="text-xs text-slate-500">— {f.description}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default function PollutionEvents() {
  const [stations, setStations] = useState<Station[]>([])
  const [selected, setSelected] = useState('Anand Vihar')
  const [data, setData] = useState<PollutionEventsCurrent | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getEvents(selected)
      .then((r) => setData(r.data))
      .catch((e) => setError(e?.response?.data?.detail ?? 'Failed to load pollution events'))
      .finally(() => setLoading(false))
  }, [selected])

  useEffect(() => {
    getStations().then((r) => setStations(r.data)).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Pollution Events"
        subtitle="Model-detected surges, relief windows and high-risk episodes from the trained PM2.5 forecast series + stored atmospheric state"
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Events' }]}
        lastUpdated={data?.generated_at}
        actions={
          <select value={selected} onChange={(e) => setSelected(e.target.value)} className="select" aria-label="Select station">
            {stations.map((s) => (
              <option key={s.id} value={s.name}>{s.name}</option>
            ))}
          </select>
        }
      />

      {error && <ErrorState title="Events unavailable" message={error} onRetry={load} />}

      {loading ? (
        <LoadingState label="Detecting forecast events" rows={2} />
      ) : data ? (
        <>
          {data.methodology?.detection_window_hours != null && (
            <div className="card flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-600">
              <span>Model: <span className="font-semibold text-slate-900">{data.model}</span></span>
              {data.uncertainty_method && <span>Uncertainty: <span className="font-semibold text-slate-900">{data.uncertainty_method}</span></span>}
              {data.baseline_pm25_ugm3 != null && <span>Baseline: <span className="font-semibold text-slate-900">{fmt(data.baseline_pm25_ugm3, 0)} μg/m³</span></span>}
              {data.forecast_peak_pm25_ugm3 != null && <span>Forecast peak: <span className="font-semibold text-slate-900">{fmt(data.forecast_peak_pm25_ugm3, 0)} μg/m³</span></span>}
              <span>Horizon: <span className="font-semibold text-slate-900">+{data.horizon_hours}h</span></span>
              <span>Lookback: <span className="font-semibold text-slate-900">past 48h + forecast</span></span>
            </div>
          )}

          {data.events.length ? (
            <div className="space-y-4">
              {data.events.map((ev, i) => (
                <EventCard key={i} ev={ev} />
              ))}
            </div>
          ) : (
            <EmptyState
              title="No events detected in this window"
              hint="No forecasted surge, relief or high-risk episode exceeded the documented detection thresholds for this station."
            />
          )}

          {data.notes && data.notes.length > 0 && (
            <div className="card">
              <h2 className="card-header">Methodology notes</h2>
              <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
                {data.notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            </div>
          )}
        </>
      ) : error ? null : (
        <EmptyState title="No events available" hint="Seed the database and train the PM2.5 models to detect forecast events." />
      )}
    </div>
  )
}