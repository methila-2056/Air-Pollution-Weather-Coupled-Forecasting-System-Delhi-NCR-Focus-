import { useState, useEffect } from 'react'
import { getGridForecast, getDispersionForecast, generateCoupledForecast, getStations } from '../api/client'
import PageHeader from '../components/PageHeader'
import { AQI_CATEGORIES, aqiCategoryHex, aqiStyle } from '../lib/aqi'
import type { GridForecast, CoupledForecastResult, DispersionForecast, Station, GridCell } from '../types'

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
        .catch(() => setError('Failed to load spatial forecast'))
    } else {
      getDispersionForecast(horizon, 8)
        .then(r => setDisp(r.data))
        .catch(() => setError('Failed to load numerical dispersion forecast'))
    }
    generateCoupledForecast(selStation)
      .then(r => setCoupled(r.data))
      .catch(() => {})
  }, [selStation, horizon, mode])

  const width = 480
  const height = 420
  const { lats_min, lats_max, lons_min, lons_max } = grid?.extent ?? { lats_min: 28.2, lats_max: 28.9, lons_min: 76.6, lons_max: 77.5 }
  const stepDeg = grid?.step_deg ?? 0.02
  const gridCols = grid?.step_deg ? Math.max(1, Math.round((lons_max - lons_min) / grid.step_deg)) : 45
  const gridRows = grid?.step_deg ? Math.max(1, Math.round((lats_max - lats_min) / grid.step_deg)) : 35
  const x = (lon: number) => ((lon - lons_min) / (lons_max - lons_min)) * width
  const y = (lat: number) => height - ((lat - lats_min) / (lats_max - lats_min)) * height

  const dispFrame = disp?.frames.find(f => f.hour === dispHour) ?? disp?.frames[disp.frames.length - 1]
  const frameCells: GridCell[] = mode === 'numerical' ? (dispFrame?.cells ?? []) : (grid?.cells ?? [])

  return (
    <div className="space-y-6">
      <PageHeader
        title="NCR Spatial AQI Forecast"
        subtitle={
          mode === 'statistical'
            ? 'High-resolution gridded AQI surface (IDW + wind advection) across Delhi NCR'
            : 'Numerical advection-diffusion dispersion of pollution plumes (72h, fire-inclusive, two-way coupled meteorology)'
        }
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Spatial Forecast' }]}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex overflow-hidden rounded-lg border border-slate-200 bg-slate-100 text-sm">
              <button
                className={`px-3 py-1.5 ${mode === 'statistical' ? 'bg-inst-700 text-white' : 'bg-transparent text-slate-600 hover:bg-slate-200'}`}
                onClick={() => setMode('statistical')}
              >
                Statistical grid
              </button>
              <button
                className={`px-3 py-1.5 ${mode === 'numerical' ? 'bg-inst-700 text-white' : 'bg-transparent text-slate-600 hover:bg-slate-200'}`}
                onClick={() => setMode('numerical')}
              >
                Numerical dispersion
              </button>
            </div>
            <select value={selStation} onChange={e => setSelStation(e.target.value)} className="select" aria-label="Select station">
              {stations.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
            </select>
            <select
              value={horizon}
              onChange={e => { const h = Number(e.target.value); setHorizon(h); setDispHour(h) }}
              className="select"
              aria-label="Forecast horizon"
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
        }
      />

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Heatmap */}
        <div className="card p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="font-semibold text-slate-900">
              {mode === 'numerical' ? `Advected AQI Field — t+${dispFrame?.hour ?? horizon}h` : `AQI Surface — t+${horizon}h`}
            </h3>
            {mode === 'numerical' && disp ? (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <label>hour</label>
                <select value={dispHour} onChange={e => setDispHour(Number(e.target.value))} className="select !w-auto !py-0.5">
                  {disp.frames.map(f => <option key={f.hour} value={f.hour}>t+{f.hour}</option>)}
                </select>
              </div>
            ) : null}
          </div>
          <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full rounded-lg border border-slate-200 bg-slate-100">
            {frameCells.map((c, i) => (
              <rect
                key={i}
                x={x(c.lon)}
                y={y(c.lat)}
                width={width / gridCols}
                height={height / gridRows}
                fill={c.aqi != null ? aqiStyle(c.aqi).hex : aqiCategoryHex(c.aqi_category)}
                opacity={0.85}
              />
            ))}
            {stations.map(s => (
              <circle key={s.id} cx={x(s.longitude)} cy={y(s.latitude)} r={4} fill="#fff" stroke="#0f172a" strokeWidth={1} />
            ))}
            {(mode === 'numerical' ? disp?.fires ?? [] : []).map((f, i) => (
              <circle key={i} cx={x(f.lon)} cy={y(f.lat)} r={5} fill="#f97316" stroke="#7c2d12" strokeWidth={1.5} opacity={0.9} />
            ))}
          </svg>
          <div className="mt-3 flex flex-wrap gap-3">
            {AQI_CATEGORIES.map((cat) => (
              <div key={cat.label} className="flex items-center gap-1 text-xs text-slate-600">
                <span className="h-3 w-3 rounded" style={{ background: cat.hex }} />
                {cat.label}
              </div>
            ))}
          </div>
        </div>

        {/* Right column: coupling feedback + numerical diagnostics */}
        <div className="space-y-4">
          {mode === 'numerical' && disp && dispFrame && (
            <div className="card p-4 text-sm">
              <h3 className="mb-2 font-semibold text-slate-900">Dispersion Diagnostics — t+{dispFrame.hour}h</h3>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="rounded bg-slate-100 p-2">
                  <p className="text-xs text-slate-500">Mean AQI</p>
                  <p className="text-lg font-semibold text-slate-900">{dispFrame.aqi_mean}</p>
                </div>
                <div className="rounded bg-slate-100 p-2">
                  <p className="text-xs text-slate-500">Max AQI</p>
                  <p className="text-lg font-semibold text-slate-900">{dispFrame.aqi_max}</p>
                </div>
                <div className="rounded bg-slate-100 p-2">
                  <p className="text-xs text-slate-500">Fires</p>
                  <p className="text-lg font-semibold text-slate-900">{disp.fire_count}</p>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-500">
                <span>Wind: <b className="text-slate-900">{dispFrame.wind_speed} m/s @ {dispFrame.wind_dir_deg}°</b></span>
                <span>PBL: <b className="text-slate-900">{dispFrame.pbl_height} m</b></span>
                <span>Precip: <b className="text-slate-900">{dispFrame.precip_mm} mm</b></span>
                <span>Integration dt: <b className="text-slate-900">{disp.dt_used}s</b></span>
              </div>
              <div className="mt-3">
                <p className="mb-1 text-xs font-semibold text-slate-500">Two-way coupling feedback (chemistry → meteorology):</p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded bg-slate-100 p-2">
                    <span className="text-slate-500">Stability index </span>
                    <span className="font-semibold text-emerald-600">{dispFrame.coupling.stability_coupling_index.toFixed(3)}</span>
                  </div>
                  <div className="rounded bg-slate-100 p-2">
                    <span className="text-slate-500">PBL suppression </span>
                    <span className="font-semibold text-emerald-600">{dispFrame.coupling.pbl_suppression_factor.toFixed(3)}</span>
                  </div>
                  <div className="rounded bg-slate-100 p-2">
                    <span className="text-slate-500">Effective PBL </span>
                    <span className="font-semibold text-slate-900">{dispFrame.coupling.corrected_pbl_height.toFixed(0)}m</span>
                  </div>
                  <div className="rounded bg-slate-100 p-2">
                    <span className="text-slate-500">Mean PM2.5 </span>
                    <span className="font-semibold text-slate-900">{dispFrame.coupling.mean_pm25.toFixed(1)} µg/m³</span>
                  </div>
                </div>
              </div>
              {disp.horizon_hours > 0 && (
                <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
                  Numerical core: dC/dt = -u·grad(C) + K·laplacian(C) - (deposition + washout)·C + E. Fire plumes (orange dots) advect
                  downwind while aerosols suppress PBL and deepen stability — an explicit two-way meteorological interlink.
                </p>
              )}
            </div>
          )}

          <div className="card p-4">
            <h3 className="mb-2 font-semibold text-slate-900">Coupled Two-Way Feedback — {selStation}</h3>
            {coupled ? (
              <div className="space-y-2 text-sm">
                <p className="text-slate-500">Mode: <span className="font-semibold text-emerald-600">{coupled.mode}</span></p>
                <div className="grid grid-cols-3 gap-2">
                  {coupled.coupled.map(p => (
                    <div key={p.horizon_hours} className="rounded bg-slate-100 p-2">
                      <p className="text-xs text-slate-500">t+{p.horizon_hours}h</p>
                      <p className="font-semibold text-slate-900">AQI {p.aqi_pred}</p>
                      <p className="text-xs text-slate-500">{p.aqi_category}</p>
                      <p className="text-[10px] text-slate-500">SO2 {p.so2_pred} · CO {p.co_pred}</p>
                    </div>
                  ))}
                </div>
                <div>
                  <p className="mb-1 mt-2 text-xs font-semibold text-slate-500">PBL / stability evolution (feedback path):</p>
                  {coupled.feedback_path.slice(0, 12).map(pt => (
                    <div key={pt.t_plus} className="flex justify-between border-b border-slate-200 py-1 text-xs text-slate-600">
                      <span>t+{pt.t_plus}h</span>
                      <span>PM2.5 {pt.pm25}</span>
                      <span>PBL {pt.pbl_effective}m</span>
                      <span>stab {pt.stability}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-500">Run the coupled forecast to see the two-way weather-chemistry feedback path.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}