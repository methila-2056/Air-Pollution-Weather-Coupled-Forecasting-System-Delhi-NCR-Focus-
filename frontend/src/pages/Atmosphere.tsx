import { useState, useEffect } from 'react'
import { getStations, getWeather, getInversion } from '../api/client'
import InversionPanel from '../components/InversionPanel'
import type { Station, WeatherData, InversionData } from '../types'

export default function Atmosphere() {
  const [stations, setStations] = useState<Station[]>([])
  const [selected, setSelected] = useState('Anand Vihar')
  const [weather, setWeather] = useState<WeatherData | null>(null)
  const [inversion, setInversion] = useState<InversionData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { getStations().then(r => setStations(r.data)).catch(() => {}) }, [])
  useEffect(() => {
    setError(null)
    Promise.allSettled([
      getWeather(selected).then(r => setWeather(r.data)),
      getInversion(selected).then(r => setInversion(r.data)),
    ]).then(results => {
      if (results.every(r => r.status === 'rejected')) setError('Failed to load atmospheric data')
    })
  }, [selected])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Atmospheric Conditions</h1>
      <select value={selected} onChange={e => setSelected(e.target.value)} className="bg-navy-800 border border-navy-700 rounded-lg px-4 py-2 text-sm">
        {stations.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
      </select>
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">{error}</div>
      )}
      <div className="grid grid-cols-4 gap-4">
        <div className="card"><p className="card-header">Temperature</p><p className="stat-value">{weather?.temperature ?? '--'}°C</p></div>
        <div className="card"><p className="card-header">Humidity</p><p className="stat-value">{weather?.humidity ?? '--'}%</p></div>
        <div className="card"><p className="card-header">Wind</p><p className="stat-value">{weather?.wind_speed ?? '--'} m/s</p></div>
        <div className="card"><p className="card-header">Pressure</p><p className="stat-value">{weather?.pressure_msl ?? '--'} hPa</p></div>
      </div>
      <div className="grid grid-cols-2 gap-6">
        <InversionPanel data={inversion} />
        <div className="card">
          <h3 className="card-header">PBL Height & Ventilation</h3>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-400">Current PBL Height</span>
                <span className="font-medium">{weather?.pbl_height ? `${weather.pbl_height}m` : '--'}</span>
              </div>
              <div className="w-full bg-navy-700 rounded-full h-3">
                <div
                  className="h-3 rounded-full transition-all"
                  style={{
                    width: weather?.pbl_height ? `${Math.min(100, (weather.pbl_height / 1500) * 100)}%` : '0%',
                    backgroundColor: weather?.pbl_height && weather.pbl_height < 300 ? '#ef4444' : weather?.pbl_height && weather.pbl_height < 600 ? '#f59e0b' : '#22c55e'
                  }}
                />
              </div>
              <p className="text-xs text-gray-500 mt-2">
                {weather?.pbl_height && weather.pbl_height < 300
                  ? 'Compressed boundary layer - pollutants trapped near surface'
                  : weather?.pbl_height && weather.pbl_height < 600
                  ? 'Moderate boundary layer - limited vertical mixing'
                  : weather?.pbl_height
                  ? 'Elevated boundary layer - good dispersion conditions'
                  : 'PBL height data unavailable'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
