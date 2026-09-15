import { useEffect, useState } from 'react'
import { MapPin, Route, Wind } from 'lucide-react'
import { getStations, getFireHotspots, getPlumeRisk, getPollutionLatest } from '../api/client'
import StationMap from '../components/StationMap'
import PageHeader from '../components/PageHeader'
import ErrorState from '../components/ErrorState'
import EmptyState from '../components/EmptyState'
import { aqiStyle, fmt } from '../lib/aqi'
import type { Station, FireHotspot, PlumeRisk, PollutionReading } from '../types'

export default function NCRMap() {
  const [stations, setStations] = useState<Station[]>([])
  const [fires, setFires] = useState<FireHotspot[]>([])
  const [plume, setPlume] = useState<PlumeRisk | null>(null)
  const [pollution, setPollution] = useState<PollutionReading[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getStations()
      .then((r) => setStations(r.data))
      .catch(() => setError('Failed to load station data'))
    getFireHotspots()
      .then((r) => setFires(r.data.hotspots))
      .catch(() => {})
    getPlumeRisk()
      .then((r) => setPlume(r.data))
      .catch(() => {})
    getPollutionLatest()
      .then((r) => setPollution(r.data))
      .catch(() => {})
  }, [])

  const latestByStation = new Map<number, PollutionReading>()
  pollution.forEach((p) => {
    if (!latestByStation.has(p.station_id)) latestByStation.set(p.station_id, p)
  })

  const riskTone =
    plume?.risk_level === 'HIGH' ? 'bg-red-100 text-red-800' :
    plume?.risk_level === 'MODERATE' ? 'bg-amber-100 text-amber-800' :
    'bg-green-100 text-green-800'

  return (
    <div className="space-y-6">
      <PageHeader
        title="Delhi NCR Monitoring Map"
        subtitle="CPCB air-quality stations, NASA FIRMS fire hotspots and plume-transport context"
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'NCR Map' }]}
        lastUpdated={undefined}
      />

      {error && <ErrorState message={error} onRetry={() => window.location.reload()} />}

      <div className="card overflow-hidden p-0">
        <StationMap stations={stations} fires={fires} pollution={pollution} />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="card flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-inst-50">
            <MapPin className="h-5 w-5 text-inst-700" aria-hidden="true" />
          </span>
          <div>
            <p className="text-xs text-slate-500">Hotspots (24 h region)</p>
            <p className="text-xl font-bold text-slate-900">{fires.length}</p>
          </div>
        </div>
        <div className={`card flex items-center gap-3 ${plume ? '' : 'opacity-60'}`}>
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100">
            <Wind className={riskTone.split(' ')[1] ?? 'text-slate-600'} aria-hidden="true" />
          </span>
          <div>
            <p className="text-xs text-slate-500">Plume transport risk</p>
            <p className={`text-xl font-bold ${riskTone.split(' ')[1] ?? 'text-slate-900'}`}>{plume?.risk_level ?? '--'}</p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-100">
            <Route className="h-5 w-5 text-slate-600" aria-hidden="true" />
          </span>
          <div>
            <p className="text-xs text-slate-500">Smoke arrival (nearest)</p>
            <p className="text-xl font-bold text-slate-900">
              {plume?.transport_time_hours != null ? `${plume.transport_time_hours.toFixed(1)}h` : '--'}
            </p>
          </div>
        </div>
      </div>

      <div className="card">
        <h2 className="mb-3 text-base font-bold text-slate-900">Station AQI snapshot</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          {stations.map((s) => {
            const reading = latestByStation.get(s.id)
            const style = aqiStyle(reading?.aqi ?? null)
            return (
              <div key={s.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <div className="flex items-center justify-between gap-1">
                  <p className="truncate text-xs font-semibold text-slate-800">{s.name}</p>
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${style.bar}`} aria-hidden="true" />
                </div>
                <p className="text-[10px] text-slate-500">
                  {s.latitude.toFixed(3)}, {s.longitude.toFixed(3)}{s.state ? ` · ${s.state}` : ''}
                </p>
                <p className="mt-1 text-sm text-slate-700">
                  {reading ? (
                    <>
                      AQI <span className="font-bold tabular-nums text-slate-900">{reading.aqi?.toFixed(0) ?? '--'}</span>
                      <span className="text-xs text-slate-500"> · PM2.5 {fmt(reading.pm25, 0)}</span>
                    </>
                  ) : (
                    <span className="italic text-slate-400">No reading yet</span>
                  )}
                </p>
              </div>
            )
          })}
          {!stations.length && <EmptyState title="No stations loaded" />}
        </div>
      </div>
    </div>
  )
}