import { useState, useEffect } from 'react'
import { getGridForecast, generateCoupledForecast, getStations } from '../api/client'
import type { GridForecast, CoupledForecastResult, Station } from '../types'

const AQI_COLORS: Record<string, string> = {
  Good: '#22c55e',
  Satisfactory: '#84cc16',
  Moderate: '#eab308',
  Poor: '#f97316',
  'Very Poor': '#ef4444',
  Severe: '#7f1d1d',
}

const HORIZONS = [1, 6, 12, 24, 48, 72]

export default function SpatialForecastPage() {
  const [grid, setGrid] = useState<GridForecast | null>(null)
  const [coupled, setCoupled] = useState<CoupledForecastResult | null>(null)
  const [stations, setStations] = useState<Station[]>([])
  const [horizon, setHorizon] = useState(24)
  const [selStation, setSelStation] = useState('Anand Vihar')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getStations().then(r => setStations(r.data)).catch(() => setError('Failed to load stations'))
  }, [])

  useEffect(() => {
    if (!selStation) return
    setError(null)
    getGridForecast(horizon)
      .then(r => setGrid(r.data))
      .catch(e => setError('Failed to load spatial forecast'))
    // warm the coupled forecast cache for the selected station
    generateCoupledForecast(selStation)
      .then(r => setCoupled(r.data))
      .catch(() => {})
  }, [selStation, horizon])

  const width = 480
  const height = 420
  const { lats_min, lats_max, lons_min, lons_max } = grid?.extent ?? { lats_min: 28.2, lats_max: 28.9, lons_min: 76.6, lons_max: 77.5 }
  const x = (lon: number) => ((lon - lons_min) / (lons_max - lons_min)) * width
  const y = (lat: number) => height - ((lat - lats_min) / (lats_max - lats_min)) * height

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold">NCR Spatial AQI Forecast</h1>
          <p className="text-sm text-gray-400">High-resolution gridded AQI surface (IDW + wind advection) across Delhi NCR</p>
        </div>
        <div className="flex gap-2 items-center">
          <select value={selStation} onChange={e => setSelStation(e.target.value)} className="select">
            {stations.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
          </select>
          <select value={horizon} onChange={e => setHorizon(Number(e.target.value))} className="select">
            {HORIZONS.map(h => <option key={h} value={h}>t+{h}h</option>)}
          </select>
          <button
            className="btn-primary"
            onClick={() => { setLoading(true); generateCoupledForecast(selStation).then(r => setCoupled(r.data)).catch(() => setError('Failed to run coupled forecast')).finally(() => setLoading(false)) }}
          >
            {loading ? 'Running...' : 'Run Coupled'}
          </button>
        </div>
      </div>

      {error && <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Heatmap */}
        <div className="card p-4">
          <h3 className="font-semibold mb-2">AQI Surface — t+{horizon}h</h3>
          <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto bg-gray-900 rounded-lg">
            {grid?.cells.map((c, i) => (
              <rect
                key={i}
                x={x(c.lon)}
                y={y(c.lat)}
                width={width / 45}
                height={height / 35}
                fill={AQI_COLORS[c.aqi_category] ?? '#3f3f46'}
                opacity={0.85}
              />
            ))}
            {stations.map(s => (
              <circle key={s.id} cx={x(s.longitude)} cy={y(s.latitude)} r={4} fill="#fff" stroke="#000" strokeWidth={1} />
            ))}
          </svg>
          <div className="flex gap-3 mt-3 flex-wrap">
            {Object.entries(AQI_COLORS).map(([cat, col]) => (
              <div key={cat} className="flex items-center gap-1 text-xs">
                <span className="w-3 h-3 rounded" style={{ background: col }} />
                {cat}
              </div>
            ))}
          </div>
        </div>

        {/* Coupled feedback details */}
        <div className="card p-4">
          <h3 className="font-semibold mb-2">Coupled Two-Way Feedback — {selStation}</h3>
          {coupled ? (
            <div className="space-y-2 text-sm">
              <p className="text-gray-400">Mode: <span className="text-emerald-400">{coupled.mode}</span></p>
              <div className="grid grid-cols-3 gap-2">
                {coupled.coupled.map(p => (
                  <div key={p.horizon_hours} className="bg-gray-800/60 rounded p-2">
                    <p className="text-xs text-gray-400">t+{p.horizon_hours}h</p>
                    <p className="font-semibold">AQI {p.aqi_pred}</p>
                    <p className="text-xs text-gray-400">{p.aqi_category}</p>
                    <p className="text-[10px] text-gray-500">SO₂ {p.so2_pred} · CO {p.co_pred}</p>
                  </div>
                ))}
              </div>
              <div>
                <p className="text-xs font-semibold text-gray-400 mt-2 mb-1">PBL / stability evolution (feedback path):</p>
                {coupled.feedback_path.slice(0, 12).map(pt => (
                  <div key={pt.t_plus} className="flex justify-between text-xs border-b border-gray-800 py-1">
                    <span>t+{pt.t_plus}h</span>
                    <span>PM₂.₅ {pt.pm25}</span>
                    <span>PBL {pt.pbl_effective}m</span>
                    <span>stab {pt.stability}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-400">Run the coupled forecast to see the two-way weather-chemistry feedback path.</p>
          )}
        </div>
      </div>
    </div>
  )
}