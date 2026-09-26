import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, Scale } from 'lucide-react'
import { getAlerts, getGrapCurrent } from '../api/client'
import PageHeader from '../components/PageHeader'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import EmptyState from '../components/EmptyState'
import AlertList from '../components/AlertList'
import GrapPanel from '../components/GrapPanel'
import GrapStagesTable from '../components/GrapStagesTable'
import { useIntervalRefresh } from '../hooks/useIntervalRefresh'
import { useStationNames } from '../components/StationsMenu'
import type { Alert, GrapAssessment } from '../types'

export default function Alerts() {
  const [params, setParams] = useSearchParams()
  const station = params.get('station') ?? ''
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [grap, setGrap] = useState<GrapAssessment | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const { names: stations } = useStationNames()

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.allSettled([
      getAlerts(station || undefined).then((r) => setAlerts(r.data)).catch(() => setAlerts([])),
      getGrapCurrent().then((r) => setGrap(r.data)).catch(() => setGrap(null)),
    ]).then((results) => {
      if (results.every((r) => r.status === 'rejected')) setError('Failed to load alerts')
    }).finally(() => setLoading(false))
  }, [station])

  useEffect(() => { load() }, [load])
  useIntervalRefresh(load, 60_000, autoRefresh)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Alerts & Warnings"
        subtitle="Model-driven pollution alerts with GRAP stage assessment"
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Alerts' }]}
        lastUpdated={alerts[0]?.created_at ?? grap?.assessed_at}
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs font-medium text-slate-500">
              Station
              <select
                aria-label="Filter alerts by station"
                value={station}
                onChange={(e) => {
                  const next = e.target.value
                  setParams(next ? { station: next } : {}, { replace: true })
                }}
                className="rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 outline-none focus:border-inst-500 focus:ring-2 focus:ring-inst-500/30"
              >
                <option value="">All NCR stations</option>
                {stations.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="inline-flex cursor-pointer select-none items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600">
              <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} className="h-3.5 w-3.5 accent-inst-700" />
              Auto-refresh (1 min)
            </label>
          </div>
        }
      />

      {error && <ErrorState title="Alert service unavailable" message={error} onRetry={load} />}

      {loading ? (
        <LoadingState label="Loading alerts" rows={2} />
      ) : (
        <>
          <section className="card">
            <div className="mb-3 flex items-center gap-2">
              <Scale className="h-4 w-4 text-inst-700" aria-hidden="true" />
              <h2 className="text-base font-bold text-slate-900">Graded Response Action Plan</h2>
            </div>
            <GrapPanel data={grap} />
            <GrapStagesTable />
          </section>

          <section className="card">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden="true" />
              <h2 className="text-base font-bold text-slate-900">
                Active alerts ({alerts.length})
              </h2>
              {station && (
                <span className="rounded-full bg-inst-50 px-2 py-0.5 text-xs font-semibold text-inst-800">
                  {station}
                </span>
              )}
            </div>
            {alerts.length ? (
              <AlertList alerts={alerts} />
            ) : (
              <EmptyState
                title="No active alerts"
                hint={
                  station
                    ? 'No warning thresholds are currently exceeded for this station.'
                    : 'No warning thresholds are currently exceeded.'
                }
              />
            )}
          </section>
        </>
      )}
    </div>
  )
}