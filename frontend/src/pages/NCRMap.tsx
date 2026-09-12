import { useState, useEffect } from 'react'
import { getStations, getFireHotspots, getPlumeRisk, getPollutionLatest } from '../api/client'
import StationMap from '../components/StationMap'
import type { Station, FireHotspot, PlumeRisk, PollutionReading } from '../types'

export default function NCRMap() {
  const [stations, setStations] = useState<Station[]>([])
  const [fires, setFires] = useState<FireHotspot[]>([])
  const [plume, setPlume] = useState<PlumeRisk | null>(null)
  const [pollution, setPollution] = useState<PollutionReading[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getStations()
      .then(r => setStations(r.data))
      .catch(() => setError('Failed to load station data'))
    getFireHotspots()
      .then(r => setFires(r.data.hotspots))
      .catch(() => {})
    getPlumeRisk()
      .then(r => setPlume(r.data))
      .catch(() => {})
    getPollutionLatest()
      .then(r => setPollution(r.data))
      .catch(() => {})
  }, [])

  const latestByStation = new Map<number, PollutionReading>()
  pollution.forEach(p => {
    if (!latestByStation.has(p.station_id)) latestByStation.set(p.station_id, p)
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Delhi NCR Monitoring Map</h1>
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">{error}</div>
      )}
      <div className="card p-0 overflow-hidden">
        <StationMap stations={stations} fires={fires} pollution={pollution} />
      </div>
      {plume && (
        <div className="card">
          <h3 className="card-header">Fire-Plume Transport (live)</h3>
          <div className="grid grid-cols-4 gap-3 text-sm">
            <div>
              <p className="text-gray-400">Hotspots (24h region)</p>
              <p className="font-semibold">{fires.length}</p>
            </div>
            <div>
              <p className="text-gray-400">Headline Risk</p>
              <p className="font-semibold">{plume.risk_level}</p>
            </div>
            <div>
              <p className="text-gray-400">Wind-Aligned</p>
              <p className="font-semibold">{plume.wind_alignment_pct != null ? `${plume.wind_alignment_pct.toFixed(0)}%` : '--'}</p>
            </div>
            <div>
              <p className="text-gray-400">Smoke Arrival (nearest)</p>
              <p className="font-semibold">{plume.transport_time_hours != null ? `${plume.transport_time_hours.toFixed(1)}h` : '--'}</p>
            </div>
          </div>
        </div>
      )}
      <div className="grid grid-cols-3 gap-4">
        {stations.map(s => {
          const reading = latestByStation.get(s.id)
          return (
            <div key={s.id} className="card">
              <h3 className="font-semibold">{s.name}</h3>
              <p className="text-sm text-gray-400">
                {s.latitude.toFixed(4)}, {s.longitude.toFixed(4)}
                {s.state ? ` · ${s.state}` : ''}
              </p>
              <p className="text-sm mt-1">
                {reading ? (
                  <>AQI <span className="font-semibold">{reading.aqi?.toFixed(0) ?? '--'}</span> · PM2.5 <span className="font-semibold">{reading.pm25?.toFixed(1) ?? '--'}</span> μg/m³</>
                ) : (
                  <span className="text-gray-400">No reading yet</span>
                )}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}