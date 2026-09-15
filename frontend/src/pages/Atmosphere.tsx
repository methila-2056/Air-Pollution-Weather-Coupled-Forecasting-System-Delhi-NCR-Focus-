import { useCallback, useEffect, useState } from 'react'
import { CloudSun, Droplets, Gauge, Thermometer, Wind } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import EmptyState from '../components/EmptyState'
import InversionPanel from '../components/InversionPanel'
import CouplingPanel from '../components/CouplingPanel'
import KpiCard from '../components/KpiCard'
import { fmt } from '../lib/aqi'
import { getStations, getWeather, getInversion, getCoupling } from '../api/client'
import type { Station, WeatherData, InversionData, CouplingData } from '../types'

export default function Atmosphere() {
  const [stations, setStations] = useState<Station[]>([])
  const [selected, setSelected] = useState('Anand Vihar')
  const [weather, setWeather] = useState<WeatherData | null>(null)
  const [inversion, setInversion] = useState<InversionData | null>(null)
  const [coupling, setCoupling] = useState<CouplingData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.allSettled([
      getWeather(selected).then((r) => setWeather(r.data)).catch(() => setWeather(null)),
      getInversion(selected).then((r) => setInversion(r.data)).catch(() => setInversion(null)),
      getCoupling(selected).then((r) => setCoupling(r.data)).catch(() => setCoupling(null)),
    ]).then((results) => {
      if (results.every((r) => r.status === 'rejected')) setError('Failed to load atmospheric data')
    }).finally(() => setLoading(false))
  }, [selected])

  useEffect(() => { getStations().then((r) => setStations(r.data)).catch(() => {}) }, [])
  useEffect(() => { load() }, [load])

  const pbl = weather?.pbl_height ?? null
  const pblWidth = pbl != null ? Math.max(4, Math.min(100, (pbl / 1500) * 100)) : 0
  const pblColor = pbl == null ? '#cbd5e1' : pbl < 300 ? '#dc2626' : pbl < 600 ? '#d97706' : '#16a34a'
  const pblNote =
    pbl == null
      ? 'PBL height data unavailable'
      : pbl < 300
        ? 'Compressed boundary layer — pollutants trapped near the surface'
        : pbl < 600
          ? 'Moderate boundary layer — limited vertical mixing'
          : 'Elevated boundary layer — good dispersion conditions'

  const ventilation = pbl != null && (weather?.wind_speed ?? null) != null ? pbl * (weather?.wind_speed ?? 0) : null

  return (
    <div className="space-y-6">
      <PageHeader
        title="Atmospheric Conditions"
        subtitle="Vertical structure, inversion trapping and weather-chemistry coupling"
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Atmosphere' }]}
        lastUpdated={weather?.timestamp}
        actions={
          <select value={selected} onChange={(e) => setSelected(e.target.value)} className="select" aria-label="Select station">
            {stations.map((s) => (
              <option key={s.id} value={s.name}>{s.name}</option>
            ))}
          </select>
        }
      />

      {error && <ErrorState title="Atmospheric data unavailable" message={error} onRetry={load} />}

      {loading && !weather ? (
        <LoadingState label="Loading atmospheric data" rows={2} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KpiCard label="Temperature" value={fmt(weather?.temperature, 1)} unit="°C" tone={weather?.temperature != null && weather.temperature > 35 ? 'warn' : 'default'} />
            <KpiCard label="Humidity" value={fmt(weather?.humidity, 0)} unit="%" />
            <KpiCard label="Wind speed" value={fmt(weather?.wind_speed, 1)} unit="m/s" />
            <KpiCard label="Pressure (MSL)" value={fmt(weather?.pressure_msl, 0)} unit="hPa" />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <CouplingPanel data={coupling} />

            <div className="card">
              <div className="flex items-center gap-2">
                <CloudSun className="h-4 w-4 text-inst-700" aria-hidden="true" />
                <h3 className="card-header mb-0">PBL height & ventilation</h3>
              </div>
              <div className="mt-4">
                <div className="mb-1 flex justify-between text-sm">
                  <span className="text-slate-500">Current PBL height</span>
                  <span className="font-semibold text-slate-900">{pbl != null ? `${pbl}m` : '--'}</span>
                </div>
                <div className="h-3 w-full rounded-full bg-slate-200">
                  <div className="h-3 rounded-full transition-all" style={{ width: `${pblWidth}%`, backgroundColor: pblColor }} />
                </div>
                <p className="mt-2 text-xs text-slate-500">{pblNote}</p>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Ventilation index</p>
                  <p className="text-base font-bold text-slate-900">{ventilation != null ? fmt(ventilation, 0) : '--'} <span className="text-xs text-slate-400">m²/s</span></p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Wind direction</p>
                  <p className="text-base font-bold text-slate-900">{fmt(weather?.wind_direction, 0)}°</p>
                </div>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-slate-500">
                Ventilation index = wind speed × PBL height. Low values indicate limited
                atmospheric dilution capacity, which the aerosol-PBL coupling module further modulates.
              </p>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <InversionPanel data={inversion} />
            <div className="card">
              <h3 className="card-header">What to look for</h3>
              <ul className="space-y-2 text-sm text-slate-600">
                <li className="flex items-start gap-2"><Thermometer className="mt-0.5 h-4 w-4 shrink-0 text-inst-600" aria-hidden="true" /> Inversion strength from the vertical lapse rate or PBL proxy.</li>
                <li className="flex items-start gap-2"><Wind className="mt-0.5 h-4 w-4 shrink-0 text-inst-600" aria-hidden="true" /> Whether regional winds advect plume-loads toward/away from NCR.</li>
                <li className="flex items-start gap-2"><Droplets className="mt-0.5 h-4 w-4 shrink-0 text-inst-600" aria-hidden="true" /> Both pollution trapping and dispersion are scored for each station.</li>
                <li className="flex items-start gap-2"><Gauge className="mt-0.5 h-4 w-4 shrink-0 text-inst-600" aria-hidden="true" /> Coupling panel shows the two-way aerosol–PBL feedback used by forecasts.</li>
              </ul>
            </div>
          </div>

          {!weather && !inversion && !coupling && (
            <EmptyState title="No atmospheric data" hint="This station has no weather or vertical-profile observations stored yet." />
          )}
        </>
      )}
    </div>
  )
}