import { useCallback, useEffect, useState } from 'react'
import { Flame, Info } from 'lucide-react'
import { getPlumeRisk, getFireActivity, getFireHotspots } from '../api/client'
import PageHeader from '../components/PageHeader'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import EmptyState from '../components/EmptyState'
import StubblePlume from '../components/StubblePlume'
import StationMap from '../components/StationMap'
import KpiCard from '../components/KpiCard'
import { fmt } from '../lib/aqi'
import type { PlumeRisk, FireActivity, FireHotspot } from '../types'

export default function StubblePlumePage() {
  const [risk, setRisk] = useState<PlumeRisk | null>(null)
  const [fire, setFire] = useState<FireActivity | null>(null)
  const [hotspots, setHotspots] = useState<FireHotspot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.allSettled([
      getPlumeRisk().then((r) => setRisk(r.data)).catch(() => setRisk(null)),
      getFireActivity().then((r) => setFire(r.data)).catch(() => setFire(null)),
      getFireHotspots()
        .then((r) => setHotspots(r.data.hotspots))
        .catch(() => setHotspots([])),
    ]).then((results) => {
      if (results.every((r) => r.status === 'rejected')) setError('Failed to load fire data')
    }).finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Fire & Plume Intelligence"
        subtitle="Crop-residue burning hotspots, fire radiative power and transport risk toward Delhi NCR"
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Fire & Plume' }]}
        lastUpdated={fire?.date ?? undefined}
      />

      {error && <ErrorState title="Fire data unavailable" message={error} onRetry={load} />}

      {loading && !fire ? (
        <LoadingState label="Loading fire intelligence" rows={2} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard label="Total fires (24 h)" value={fire?.total_fires ?? 0} tone={fire?.total_fires ? 'warn' : 'default'} />
            <KpiCard label="High confidence" value={fire?.high_confidence_fires ?? '--'} />
            <KpiCard label="Mean fire radiative power" value={fmt(fire?.mean_frp, 1)} unit="MW" />
            <KpiCard label="Source region" value={fire?.region ?? 'NCR periphery'} sub={fire?.date?.replace('T', ' ').slice(0, 16) ?? undefined} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <StubblePlume data={risk} />
            <div className="card">
              <div className="mb-2 flex items-center gap-2">
                <Info className="h-4 w-4 text-inst-700" aria-hidden="true" />
                <h3 className="card-header mb-0">Methodology</h3>
              </div>
              <div className="space-y-2 text-sm text-slate-600">
                <p>This module estimates regional fire-plume transport risk based on:</p>
                <ul className="list-inside list-disc space-y-1">
                  <li>NASA FIRMS active-fire hotspot locations</li>
                  <li>Fire Radiative Power (FRP) intensity</li>
                  <li>Wind direction and speed alignment</li>
                  <li>Distance from Delhi NCR</li>
                  <li>Atmospheric dispersion conditions</li>
                </ul>
                <p className="mt-3 text-amber-800">
                  Note: this is an estimated transport-risk indicator derived from satellite
                  hotspots + NWP winds — not a full regional chemical-transport simulation.
                </p>
              </div>
            </div>
          </div>

          <div className="card overflow-hidden p-0">
            <div className="flex items-center gap-2 px-6 pt-5">
              <Flame className="h-4 w-4 text-orange-600" aria-hidden="true" />
              <h2 className="text-base font-bold text-slate-900">Active hotspot map</h2>
              <span className="ml-auto text-xs text-slate-500">circle colour/size scale with FRP intensity</span>
            </div>
            <div className="p-3">
              {hotspots.length ? (
                <StationMap stations={[]} fires={hotspots} />
              ) : (
                <EmptyState title="No active hotspots" hint="No FIRMS detections in the recent window." />
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}