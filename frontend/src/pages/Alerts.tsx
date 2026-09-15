import { useEffect, useState } from 'react'
import { AlertTriangle, Scale } from 'lucide-react'
import { getAlerts, getGrapCurrent } from '../api/client'
import PageHeader from '../components/PageHeader'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import EmptyState from '../components/EmptyState'
import AlertList from '../components/AlertList'
import GrapPanel from '../components/GrapPanel'
import { useIntervalRefresh } from '../hooks/useIntervalRefresh'
import type { Alert, GrapAssessment } from '../types'

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [grap, setGrap] = useState<GrapAssessment | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)

  const load = () => {
    setLoading(true)
    setError(null)
    Promise.allSettled([
      getAlerts().then((r) => setAlerts(r.data)).catch(() => setAlerts([])),
      getGrapCurrent().then((r) => setGrap(r.data)).catch(() => setGrap(null)),
    ]).then((results) => {
      if (results.every((r) => r.status === 'rejected')) setError('Failed to load alerts')
    }).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])
  useIntervalRefresh(load, 60_000, autoRefresh)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Alerts & Warnings"
        subtitle="Model-driven pollution alerts with GRAP stage assessment"
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Alerts' }]}
        lastUpdated={alerts[0]?.created_at ?? grap?.assessed_at}
        actions={
          <label className="inline-flex cursor-pointer select-none items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600">
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} className="h-3.5 w-3.5 accent-inst-700" />
            Auto-refresh (1 min)
          </label>
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
          </section>

          <section className="card">
            <div className="mb-3 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden="true" />
              <h2 className="text-base font-bold text-slate-900">Active alerts ({alerts.length})</h2>
            </div>
            {alerts.length ? (
              <AlertList alerts={alerts} />
            ) : (
              <EmptyState title="No active alerts" hint="No warning thresholds are currently exceeded." />
            )}
          </section>
        </>
      )}
    </div>
  )
}