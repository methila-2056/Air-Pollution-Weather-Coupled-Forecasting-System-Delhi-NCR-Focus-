import type { PlumeRisk } from '../types'

export default function StubblePlume({ data }: { data: PlumeRisk | null }) {
  if (!data) return <div className="card"><p className="text-gray-400">Loading fire data...</p></div>
  
  const riskColor = {
    'HIGH': 'text-red-400 bg-red-500/20',
    'MODERATE': 'text-orange-400 bg-orange-500/20',
    'LOW': 'text-green-400 bg-green-500/20',
  }[data.risk_level] || 'text-gray-400'

  return (
    <div className="card">
      <h3 className="card-header">Regional Fire-Plume Impact</h3>
      <div className="space-y-4">
        <div className={`text-center py-3 rounded-lg ${riskColor}`}>
          <p className="text-2xl font-bold">{data.risk_level}</p>
          <p className="text-sm">Delhi NCR Impact</p>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-gray-400">Fire Count</p>
            <p className="text-lg font-bold">{data.fire_count}</p>
          </div>
          <div>
            <p className="text-gray-400">Transport</p>
            <p className="text-lg font-bold">{data.transport_direction}</p>
          </div>
          <div>
            <p className="text-gray-400">Nearest Fire</p>
            <p className="text-lg font-bold">{data.distance_nearest_fire}km</p>
          </div>
          <div>
            <p className="text-gray-400">Confidence</p>
            <p className="text-lg font-bold">{(data.confidence * 100).toFixed(0)}%</p>
          </div>
        </div>
      </div>
    </div>
  )
}
