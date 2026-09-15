import { useCallback, useEffect, useState } from 'react'
import { Download } from 'lucide-react'
import { getStations, getForecast, getForecastExportUrl } from '../api/client'
import PageHeader from '../components/PageHeader'
import LoadingState from '../components/LoadingState'
import ErrorState from '../components/ErrorState'
import EmptyState from '../components/EmptyState'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { fmt } from '../lib/aqi'
import type { Station, ForecastPoint } from '../types'

const TAB_COLORS: Record<string, string> = {
  aqi_pred: '#0B4F8A',
  pm25_pred: '#dc2626',
  pm10_pred: '#d97706',
  o3_pred: '#059669',
  no2_pred: '#7c3aed',
}

const tabs = [
  { key: 'aqi_pred', label: 'AQI' },
  { key: 'pm25_pred', label: 'PM2.5' },
  { key: 'pm10_pred', label: 'PM10' },
  { key: 'o3_pred', label: 'O₃' },
  { key: 'no2_pred', label: 'NO₂' },
]

export default function Forecast72h() {
  const [stations, setStations] = useState<Station[]>([])
  const [selectedStation, setSelectedStation] = useState('Anand Vihar')
  const [forecast, setForecast] = useState<ForecastPoint[]>([])
  const [pollutant, setPollutant] = useState<string>('aqi_pred')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getForecast(selectedStation)
      .then((r) => setForecast(r.data))
      .catch(() => setError('Failed to load forecast data'))
      .finally(() => setLoading(false))
  }, [selectedStation])

  useEffect(() => {
    getStations().then((r) => setStations(r.data)).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  const chartData = forecast.map((f) => ({
    time: `+${f.horizon_hours}h`,
    value: f[pollutant as keyof ForecastPoint] ?? null,
    category: f.aqi_category,
  }))

  return (
    <div className="space-y-6">
      <PageHeader
        title="72-Hour Forecast"
        subtitle="Hourly ML forecasts for every NCR monitoring station, with full AQI categorisation"
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Forecast' }]}
        lastUpdated={forecast[0]?.timestamp}
        actions={
          <div className="flex items-center gap-2">
            <select
              value={selectedStation}
              onChange={(e) => setSelectedStation(e.target.value)}
              className="select"
              aria-label="Select station"
            >
              {stations.map((s) => (
                <option key={s.id} value={s.name}>{s.name}</option>
              ))}
            </select>
            <a
              href={getForecastExportUrl(selectedStation, 72)}
              className="btn-outline inline-flex items-center gap-1.5"
            >
              <Download className="h-4 w-4" aria-hidden="true" /> CSV
            </a>
          </div>
        }
      />

      {error && <ErrorState title="Forecast unavailable" message={error} onRetry={load} />}

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Pollutant selection">
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={pollutant === t.key}
            onClick={() => setPollutant(t.key)}
            className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
              pollutant === t.key
                ? 'border-inst-700 bg-inst-700 text-white'
                : 'border-slate-300 bg-white text-slate-600 hover:border-inst-300 hover:text-inst-800'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <LoadingState label="Loading forecast" rows={2} />
      ) : error ? null : forecast.length ? (
        <>
          <div className="card">
            <h2 className="mb-3 text-base font-bold text-slate-900">
              {tabs.find((t) => t.key === pollutant)?.label} forecast — {selectedStation}
            </h2>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData} margin={{ left: -12, right: 12 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8 }}
                  labelStyle={{ color: '#334155' }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="value" stroke={TAB_COLORS[pollutant] ?? '#0B4F8A'} strokeWidth={2.5} dot={false} name={pollutant.replace('_pred', '').toUpperCase()} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h2 className="card-header">Forecast table</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-slate-500">
                    <th className="py-2">Horizon</th>
                    <th className="py-2 text-right">PM2.5</th>
                    <th className="py-2 text-right">PM10</th>
                    <th className="py-2 text-right">O₃</th>
                    <th className="py-2 text-right">NO₂</th>
                    <th className="py-2 text-right">AQI</th>
                    <th className="py-2 text-right">Category</th>
                  </tr>
                </thead>
                <tbody>
                  {forecast.map((f) => (
                    <tr key={f.horizon_hours} className="border-b border-slate-100">
                      <td className="py-2 font-medium text-slate-900">+{f.horizon_hours}h</td>
                      <td className="py-2 text-right tabular-nums text-slate-700">{fmt(f.pm25_pred, 1)}</td>
                      <td className="py-2 text-right tabular-nums text-slate-700">{fmt(f.pm10_pred, 1)}</td>
                      <td className="py-2 text-right tabular-nums text-slate-700">{fmt(f.o3_pred, 1)}</td>
                      <td className="py-2 text-right tabular-nums text-slate-700">{fmt(f.no2_pred, 1)}</td>
                      <td className="py-2 text-right font-bold tabular-nums text-slate-900">{f.aqi_pred ?? '--'}</td>
                      <td className="py-2 text-right"><span className="capitalize text-slate-700">{f.aqi_category}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <EmptyState title="No forecast stored" hint="Persisted forecasts for this station have not been generated yet." />
      )}
    </div>
  )
}