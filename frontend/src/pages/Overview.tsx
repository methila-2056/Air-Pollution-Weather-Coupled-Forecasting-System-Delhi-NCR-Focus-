import { useState, useEffect } from 'react'
import { getStations, getCurrentAQI, getForecast, getWeather, getInversion, getFireActivity, getPlumeRisk, getExplanation, getCoupling, getSummary, getForecastExportUrl } from '../api/client'
import AQICard from '../components/AQICard'
import AQIBadge from '../components/AQIBadge'
import StatCard from '../components/StatCard'
import ForecastChart from '../components/ForecastChart'
import InversionPanel from '../components/InversionPanel'
import CouplingPanel from '../components/CouplingPanel'
import StubblePlume from '../components/StubblePlume'
import ExplainabilityPanel from '../components/ExplainabilityPanel'
import { useIntervalRefresh } from '../hooks/useIntervalRefresh'
import type { Station, CurrentAQI, ForecastPoint, WeatherData, InversionData, FireActivity, PlumeRisk, Explanation, CouplingData, SummaryResponse } from '../types'

export default function Overview() {
  const [stations, setStations] = useState<Station[]>([])
  const [selectedStation, setSelectedStation] = useState('Anand Vihar')
  const [aqi, setAqi] = useState<CurrentAQI | null>(null)
  const [forecast, setForecast] = useState<ForecastPoint[]>([])
  const [weather, setWeather] = useState<WeatherData | null>(null)
  const [inversion, setInversion] = useState<InversionData | null>(null)
  const [fire, setFire] = useState<FireActivity | null>(null)
  const [plumeRisk, setPlumeRisk] = useState<PlumeRisk | null>(null)
  const [explanation, setExplanation] = useState<Explanation | null>(null)
  const [coupling, setCoupling] = useState<CouplingData | null>(null)
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getStations()
      .then(res => setStations(res.data))
      .catch(() => setStations([]))
  }, [])

  const refreshAll = (): Promise<void> => {
    setError(null)
    return Promise.allSettled([
      getCurrentAQI(selectedStation).then(r => setAqi(r.data)),
      getForecast(selectedStation).then(r => setForecast(r.data)),
      getWeather(selectedStation).then(r => setWeather(r.data)),
      getInversion(selectedStation).then(r => setInversion(r.data)),
      getFireActivity().then(r => setFire(r.data)),
      getPlumeRisk().then(r => setPlumeRisk(r.data)),
      getExplanation(selectedStation).then(r => setExplanation(r.data)),
      getCoupling(selectedStation).then(r => setCoupling(r.data)),
      getSummary().then(r => setSummary(r.data)),
    ]).then(results => {
      const failures = results.filter(r => r.status === 'rejected')
      if (failures.length === results.length) {
        setError('Unable to reach the backend. Make sure the API server is running.')
      }
    })
  }

  useEffect(() => {
    setLoading(true)
    refreshAll().finally(() => setLoading(false))
  }, [selectedStation])

  useIntervalRefresh(refreshAll, 60_000, autoRefresh)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Delhi NCR Air Intelligence</h1>
          <p className="text-gray-400 text-sm">Real-time monitoring & 72-hour forecasting</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={e => setAutoRefresh(e.target.checked)}
              className="accent-blue-500"
            />
            Auto-refresh (1 min)
          </label>
          <a
            href={getForecastExportUrl(selectedStation, 72)}
            className="bg-navy-700 hover:bg-navy-600 border border-navy-600 rounded-lg px-4 py-2 text-sm"
          >
            Export CSV
          </a>
          <select
            value={selectedStation}
            onChange={e => setSelectedStation(e.target.value)}
            className="bg-navy-800 border border-navy-700 rounded-lg px-4 py-2 text-sm"
          >
            {stations.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
            {!stations.length && <option>Anand Vihar</option>}
          </select>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="NCR Average AQI"
            value={summary.ncr_avg_aqi?.toFixed(0) ?? '--'}
            sub={`${summary.stations_with_readings} / ${summary.stations} stations reporting`}
            tone={summary.ncr_avg_aqi != null ? (summary.ncr_avg_aqi <= 100 ? 'good' : summary.ncr_avg_aqi >= 200 ? 'bad' : 'warn') : 'default'}
          />
          <div className="card">
            <p className="card-header">Worst Station</p>
            {summary.worst_station ? (
              <div className="mt-1 flex items-center gap-2">
                <span className="stat-value">{summary.worst_station.name}</span>
                <AQIBadge category={summary.worst_station.aqi_category} aqi={summary.worst_station.aqi} />
              </div>
            ) : <p className="stat-value">--</p>}
          </div>
          <StatCard label="Active Fires (24h)" value={summary.active_fires_24h} sub="NASA FIRMS hotspots" tone={summary.active_fires_24h > 10 ? 'bad' : 'default'} />
          <StatCard label="Open Alerts" value={summary.open_alerts} sub={`${summary.models_trained} models trained`} tone={summary.open_alerts > 0 ? 'warn' : 'good'} />
        </div>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">
          {error}
        </div>
      )}

      {loading && <div className="text-center py-12 text-gray-400">Loading data...</div>}

      <div className="grid grid-cols-4 gap-4">
        <AQICard label="AQI" value={aqi?.aqi} />
        <AQICard label="PM2.5" value={aqi?.pm25} unit="μg/m³" />
        <AQICard label="PM10" value={aqi?.pm10} unit="μg/m³" />
        <AQICard label="Category" value={aqi?.aqi_category ?? '--'} />
      </div>

      <div className="grid grid-cols-3 gap-4">
        <AQICard label="Temperature" value={weather?.temperature} unit="°C" />
        <AQICard label="Humidity" value={weather?.humidity} unit="%" />
        <AQICard label="Wind Speed" value={weather?.wind_speed} unit="m/s" />
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div>
          <h2 className="text-lg font-semibold mb-3">72-Hour AQI Forecast</h2>
          <ForecastChart data={forecast} pollutant="aqi_pred" color="#3b82f6" />
        </div>
        <InversionPanel data={inversion} />
      </div>

      <div className="grid grid-cols-2 gap-6">
        <StubblePlume data={plumeRisk} />
        <ExplainabilityPanel data={explanation} />
      </div>

      <div className="grid grid-cols-2 gap-6">
        <CouplingPanel data={coupling} />
        <InversionPanel data={inversion} />
      </div>
    </div>
  )
}
