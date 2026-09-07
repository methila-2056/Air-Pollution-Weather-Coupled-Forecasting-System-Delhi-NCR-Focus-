import { useState, useEffect } from 'react'
import { getStations } from '../api/client'
import StationMap from '../components/StationMap'
import type { Station } from '../types'

export default function NCRMap() {
  const [stations, setStations] = useState<Station[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getStations()
      .then(r => setStations(r.data))
      .catch(() => setError('Failed to load station data'))
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Delhi NCR Monitoring Map</h1>
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">{error}</div>
      )}
      <div className="card p-0 overflow-hidden">
        <StationMap stations={stations} />
      </div>
      <div className="grid grid-cols-3 gap-4">
        {stations.map(s => (
          <div key={s.id} className="card">
            <h3 className="font-semibold">{s.name}</h3>
            <p className="text-sm text-gray-400">{s.latitude.toFixed(4)}, {s.longitude.toFixed(4)}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
