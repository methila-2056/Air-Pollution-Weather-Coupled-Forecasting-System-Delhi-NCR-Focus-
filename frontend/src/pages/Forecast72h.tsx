import { useState, useEffect } from 'react'
import { getStations, getForecast } from '../api/client'
import ForecastChart from '../components/ForecastChart'
import type { Station, ForecastPoint } from '../types'

export default function Forecast72h() {
  const [stations, setStations] = useState<Station[]>([])
  const [selectedStation, setSelectedStation] = useState('Anand Vihar')
  const [forecast, setForecast] = useState<ForecastPoint[]>([])
  const [pollutant, setPollutant] = useState<'aqi_pred' | 'pm25_pred' | 'pm10_pred' | 'o3_pred' | 'no2_pred'>('aqi_pred')

  useEffect(() => { getStations().then(r => setStations(r.data)).catch(() => {}) }, [])
  useEffect(() => { getForecast(selectedStation).then(r => setForecast(r.data)).catch(() => {}) }, [selectedStation])

  const tabs = [
    { key: 'aqi_pred', label: 'AQI', color: '#3b82f6' },
    { key: 'pm25_pred', label: 'PM2.5', color: '#ef4444' },
    { key: 'pm10_pred', label: 'PM10', color: '#f59e0b' },
    { key: 'o3_pred', label: 'O₃', color: '#10b981' },
    { key: 'no2_pred', label: 'NO₂', color: '#8b5cf6' },
  ]

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">72-Hour Forecast</h1>
      <div className="flex gap-4">
        <select value={selectedStation} onChange={e => setSelectedStation(e.target.value)} className="bg-navy-800 border border-navy-700 rounded-lg px-4 py-2 text-sm">
          {stations.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
        </select>
      </div>
      <div className="flex gap-2">
        {tabs.map(t => (
          <button key={t.key} onClick={() => setPollutant(t.key as any)} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${pollutant === t.key ? 'bg-accent-blue text-white' : 'bg-navy-800 text-gray-400 hover:text-white'}`}>
            {t.label}
          </button>
        ))}
      </div>
      <ForecastChart data={forecast} pollutant={pollutant} color={tabs.find(t => t.key === pollutant)?.color} />
      <div className="card">
        <h3 className="card-header">Forecast Table</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-navy-700">
                <th className="text-left py-2">Horizon</th>
                <th className="text-right py-2">PM2.5</th>
                <th className="text-right py-2">PM10</th>
                <th className="text-right py-2">O₃</th>
                <th className="text-right py-2">NO₂</th>
                <th className="text-right py-2">AQI</th>
                <th className="text-right py-2">Category</th>
              </tr>
            </thead>
            <tbody>
              {forecast.map((f, i) => (
                <tr key={i} className="border-b border-navy-700/50">
                  <td className="py-2">+{f.horizon_hours}h</td>
                  <td className="text-right py-2">{f.pm25_pred?.toFixed(1) ?? '--'}</td>
                  <td className="text-right py-2">{f.pm10_pred?.toFixed(1) ?? '--'}</td>
                  <td className="text-right py-2">{f.o3_pred?.toFixed(1) ?? '--'}</td>
                  <td className="text-right py-2">{f.no2_pred?.toFixed(1) ?? '--'}</td>
                  <td className="text-right py-2 font-bold">{f.aqi_pred ?? '--'}</td>
                  <td className="text-right py-2">{f.aqi_category}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
