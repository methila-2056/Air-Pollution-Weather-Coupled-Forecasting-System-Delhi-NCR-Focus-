import { useState, useEffect } from 'react'
import { getGridForecast, getDispersionForecast, generateCoupledForecast, getStations } from '../api/client'
import type { GridForecast, CoupledForecastResult, DispersionForecast, Station, GridCell } from '../types'

const AQI_COLORS: Record<string, string> = {
  Good: '#22c55e',
  Satisfactory: '#84cc16',
  Moderate: '#eab308',
  Poor: '#f97316',
  'Very Poor': '#ef4444',
  Severe: '#7f1d1d',
}

const HORIZONS = [1, 6, 12, 24, 48, 72]
const DISP_HORIZONS = [24, 48, 72]
type Mode = 'statistical' | 'numerical'

export default function SpatialForecastPage() {
  const [grid, setGrid] = useState<GridForecast | null>(null)
  const [disp, setDisp] = useState<DispersionForecast | null>(null)
  const [coupled, setCoupled] = useState<CoupledForecastResult | null>(null)
  const [stations, setStations] = useState<Station[]>([])
  const [horizon, setHorizon] = useState(24)
  const [dispHour, setDispHour] = useState(24)
  const [mode, setMode] = useState<Mode>('statistical')
  const [selStation, setSelStation] = useState('Anand Vihar')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getStations().then(r => setStations(r.data)).catch(() => setError('Failed to load stations'))
  }, [])

  useEffect(() => {
    if (!selStation) return
    setError(null)
    if (mode === 'statistical') {
      getGridForecast(horizon)
        .then(r => setGrid(r.data))
        .catch(e => setError('Failed to load spatial forecast'))
    } else {
      getDispersionForecast(horizon, 8)
        .then(r => setDisp(r.data))
        .catch(e => setError('Failed to load numerical dispersion forecast'))
    }
    generateCoupledForecast(selStation)
      .then(r => setCoupled(r.data))
      .catch(() => {})
  }, [selStation, horizon, mode])

  const width = 480
  const height = 420
  const { lats_min, lats_max, lons_min, lons_max } = grid?.extent ?? { lats_min: 28.2, lats_max: 28.9, lons_min: 76.6, lons_max: 77.5 }
  const x = (lon: number) => ((lon - lons_min) / (lons_max - lons_min)) * width
  const y = (lat: number) => height - ((lat - lats_min) / (lats_max - lats_min)) * height

  const dispFrame = disp?.frames.find(f => f.hour === dispHour) ?? disp?.frames[disp.frames.length - 1]
  const frameCells: GridCell[] = mode === 'numerical' ? (dispFrame?.cells ?? []) : (grid?.cells ?? [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold">NCR Spatial AQI Forecast</h1>
          <p className="text-sm text-gray-400">
            {mode === 'statistical'
              ? 'High-resolution gridded AQI surface (IDW + wind advection) across Delhi NCR'
              : 'Numerical advection-diffusion dispersion of pollution plumes (72h, fire-inclusive, two-way coupled meteorology)'}
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <div className="flex rounded-lg overflow-hidden border border-gray-700 text-sm">
            <button
              className={`px-3 py-1.5 ${mode === 'statistical' ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-300'}`}
              onClick={() => setMode('statistical')}
            >
              Statistical grid
            </button>
            <button
              className={`px-3 py-1.5 ${mode === 'numerical' ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-300'}`}
              onClick={() => setMode('numerical')}
            >
              Numerical dispersion
            </button>
          </div>
          <select value={selStation} onChange={e => setSelStation(e.target.value)} className="select">
            {stations.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
          </select>
          <select
            value={horizon}
            onChange={e => { const h = Number(e.target.value); setHorizon(h); setDispHour(h) }}
            className="select"
          >
            {(mode === 'numerical' ? DISP_HORIZONS : HORIZONS).map(h => <option key={h} value={h}>t+{h}h</option>)}
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
          <div className="flex justify-between items-center mb-2">
            <h3 className="font-semibold">
              {mode === 'numerical' ? `Advected AQI Field — t+${dispFrame?.hour ?? horizon}h` : `AQI Surface — t+${horizon}h`}
            </h3>
            {mode === 'numerical' && disp ? (
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <label>hour</label>
                <select value={dispHour} onChange={e => setDispHour(Number(e.target.value))} className="select !w-auto !py-0.5">
                  {disp.frames.map(f => <option key={f.hour} value={f.hour}>t+{f.hour}</option>)}
                </select>
              </div>
            ) : null}
          </div>
          <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto bg-gray-900 rounded-lg">
            {frameCells.map((c, i) => (
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
            {(mode === 'numerical' ? disp?.fires ?? [] : []).map((f, i) => (
              <circle key={i} cx={x(f.lon)} cy={y(f.lat)} r={5} fill="#f97316" stroke="#7c2d12" strokeWidth={1.5} opacity={0.9} />
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

        {/* Right column: coupling feedback + numerical diagnostics */}
        <div className="space-y-4">
          {mode === 'numerical' && disp && dispFrame && (
            <div className="card p-4 text-sm">
              <h3 className="font-semibold mb-2">Dispersion Diagnostics — t+{dispFrame.hour}h</h3>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="bg-gray-800/60 rounded p-2">
                  <p className="text-xs text-gray-400">Mean AQI</p>
                  <p className="font-semibold text-lg">{dispFrame.aqi_mean}</p>
                </div>
                <div className="bg-gray-800/60 rounded p-2">
                  <p className="text-xs text-gray-400">Max AQI</p>
                  <p className="font-semibold text-lg">{dispFrame.aqi_max}</p>
                </div>
                <div className="bg-gray-800/60 rounded p-2">
                  <p className="text-xs text-gray-400">Fires</p>
                  <p className="font-semibold text-lg">{disp.fire_count}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-3 text-xs text-gray-400">
                <span>Wind: <b className="text-gray-200">{dispFrame.wind_speed} m/s @ {dispFrame.wind_dir_deg}°</b></span>
                <span>PBL: <b className="text-gray-200">{dispFrame.pbl_height} m</b></span>
                <span>Precip: <b className="text-gray-200">{dispFrame.precip_mm} mm</b></span>
                <span>Integration dt: <b className="text-gray-200">{disp.dt_used}s</b></span>
              </div>
              <div className="mt-3">
                <p className="text-xs font-semibold text-gray-400 mb-1">Two-way coupling feedback (chemistry → meteorology):</p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="bg-gray-800/60 rounded p-2">
                    <span className="text-gray-400">Stability index </span>
                    <span className="font-semibold text-emerald-300">{dispFrame.coupling.stability_coupling_index.toFixed(3)}</span>
                  </div>
                  <div className="bg-gray-800/60 rounded p-2">
                    <span className="text-gray-400">PBL suppression </span>
                    <span className="font-semibold text-emerald-300">{dispFrame.coupling.pbl_suppression_factor.toFixed(3)}</span>
                  </div>
                  <div className="bg-gray-800/60 rounded p-2">
                    <span className="text-gray-400">Effective PBL </span>
                    <span className="font-semibold text-gray-200">{dispFrame.coupling.corrected_pbl_height.toFixed(0)}m</span>
                  </div>
                  <div className="bg-gray-800/60 rounded p-2">
                    <span className="text-gray-400">Mean PM₂.₅ </span>
                    <span className="font-semibold text-gray-200">{dispFrame.coupling.mean_pm25.toFixed(1)} µg/m³</span>
                  </div>
                </div>
              </div>
              {disp.horizon_hours > 0 && (
                <p className="text-[11px] text-gray-500 mt-3">
                  Numerical core: ∂C/∂t = −u·∇C + K∇²C − (λ_dep + washout)·C + E. Fire plumes (orange dots) advect
                  downwind while aerosols suppress PBL and deepen stability — an explicit two-way meteorological interlink.
                </p>
              )}
            </div>
          )}

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
    </div>
  )
}