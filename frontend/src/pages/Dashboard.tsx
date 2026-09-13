import { useState, useEffect } from 'react'
import {
  getStations,
  getCurrentAQI,
  getForecast,
  getPm25Forecast,
  getAtmosphereCurrent,
  getFireActivity,
  getFireHotspots,
  getTransportRisk,
  getPm25ForecastExplanation,
  getModelPerformance,
  getPollutionLatest,
} from '../api/client'
import AQICard from '../components/AQICard'
import AQIBadge from '../components/AQIBadge'
import ForecastChart from '../components/ForecastChart'
import ExplainabilityPanel from '../components/ExplainabilityPanel'
import StationMap from '../components/StationMap'
import { useIntervalRefresh } from '../hooks/useIntervalRefresh'
import {
  ComposedChart,
  Area,
  Line,
  ReferenceLine,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import type {
  Station,
  CurrentAQI,
  ForecastPoint,
  Pm25ForecastResponse,
  Pm25ForecastPoint,
  AtmosphereCurrentResponse,
  FireActivity,
  FireHotspot,
  TransportRiskResponse,
  ForecastExplanation,
  ModelPerformanceResponse,
  PollutionReading,
} from '../types'

function fmt(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return v.toFixed(digits)
}

function tsFmt(s: string | null | undefined): string {
  return s ? s.replace('T', ' ').slice(0, 16) : '--'
}

function ProvenanceChip({ label }: { label: string }) {
  const styles: Record<string, string> = {
    OBSERVED: 'bg-green-500/20 text-green-300 border-green-500/50',
    DERIVED: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50',
    ESTIMATED: 'bg-amber-500/20 text-amber-300 border-amber-500/50',
    FORECAST: 'bg-blue-500/20 text-blue-300 border-blue-500/50',
    SCENARIO: 'bg-purple-500/20 text-purple-300 border-purple-500/50',
    MEASURED: 'bg-teal-500/20 text-teal-300 border-teal-500/50',
  }
  const cls = styles[label.toUpperCase()] ?? 'bg-zinc-700/40 text-zinc-300 border-zinc-600'
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${cls}`}>
      {label}
    </span>
  )
}

function SectionTitle({ icon, title, chips }: { icon: string; title: string; chips: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-lg">{icon}</span>
      <h2 className="text-base font-semibold text-white">{title}</h2>
      {chips.map(c => <ProvenanceChip key={c} label={c} />)}
    </div>
  )
}

function tickStyle() {
  return { stroke: '#6b7280', fontSize: 11 }
}

function tooltipStyle() {
  return { contentStyle: { backgroundColor: '#111640', border: '1px solid #252b68', borderRadius: 8 }, labelStyle: { color: '#9ca3af' } }
}

function buildWindArrows(stations: Station[], atmosphere: AtmosphereCurrentResponse | null): WindVectorInput[] {
  if (!atmosphere) return []
  const out: WindVectorInput[] = []
  for (const st of stations) {
    const a = atmosphere.stations.find(x => x.station === st.name)
    if (a && a.wind?.wind_direction_deg != null) {
      out.push({ lat: st.latitude, lon: st.longitude, direction_deg: a.wind.wind_direction_deg, speed: a.wind.wind_speed_mps })
    }
  }
  return out
}

interface WindVectorInput {
  lat: number
  lon: number
  direction_deg: number | null
  speed: number | null
}

function Pm25ForecastChart({ data, observed }: { data: Pm25ForecastPoint[]; observed: number | null }) {
  const rows = data.map(p => ({
    time: `+${p.forecast_horizon}h`,
    lo: p.pm25_lower_bound,
    hi: p.pm25_upper_bound,
    pred: p.predicted_pm25,
  }))
  if (observed !== null && observed !== undefined) {
    rows.unshift({ time: 'now', lo: observed, hi: observed, pred: observed })
  }
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={rows}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1a1f52" />
        <XAxis dataKey="time" {...tickStyle()} />
        <YAxis {...tickStyle()} />
        <Tooltip {...tooltipStyle()} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area dataKey="hi" stroke="none" fill="#3b82f6" fillOpacity={0.18} name="Range (upper)" />
        <Area dataKey="lo" stroke="none" fill="#111640" name="Range (lower)" />
        <Line dataKey="pred" stroke="#3b82f6" strokeWidth={2} dot={false} name="PM2.5 forecast" />
        <ReferenceLine y={60} stroke="#f59e0b" strokeDasharray="4 4" strokeWidth={1} label={{ value: 'NAAQS 60', position: 'insideTopRight', fill: '#f59e0b', fontSize: 10 }} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

export default function Dashboard() {
  const [stations, setStations] = useState<Station[]>([])
  const [selected, setSelected] = useState('Anand Vihar')
  const [current, setCurrent] = useState<CurrentAQI | null>(null)
  const [forecast, setForecast] = useState<ForecastPoint[]>([])
  const [pm25, setPm25] = useState<Pm25ForecastResponse | null>(null)
  const [atmosphere, setAtmosphere] = useState<AtmosphereCurrentResponse | null>(null)
  const [fireActivity, setFireActivity] = useState<FireActivity | null>(null)
  const [hotspots, setHotspots] = useState<FireHotspot[]>([])
  const [transport, setTransport] = useState<TransportRiskResponse | null>(null)
  const [explanation, setExplanation] = useState<ForecastExplanation | null>(null)
  const [modelPerf, setModelPerf] = useState<ModelPerformanceResponse | null>(null)
  const [pollution, setPollution] = useState<PollutionReading[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)

  useEffect(() => {
    getStations().then(r => setStations(r.data)).catch(() => setStations([]))
  }, [])

  const refreshAll = (): Promise<void> => {
    setError(null)
    return Promise.allSettled([
      getCurrentAQI(selected).then(r => setCurrent(r.data)),
      getForecast(selected).then(r => setForecast(r.data)),
      getPm25Forecast(selected).then(r => setPm25(r.data)).catch(() => setPm25(null)),
      getAtmosphereCurrent(selected).then(r => setAtmosphere(r.data)),
      getFireActivity().then(r => setFireActivity(r.data)),
      getFireHotspots().then(r => setHotspots(r.data.hotspots)),
      getTransportRisk().then(r => setTransport(r.data)),
      getPm25ForecastExplanation(selected, 24).then(r => setExplanation(r.data)).catch(() => setExplanation(null)),
      getModelPerformance().then(r => setModelPerf(r.data)),
      getPollutionLatest().then(r => setPollution(r.data)),
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
  }, [selected])

  useIntervalRefresh(refreshAll, 60_000, autoRefresh)

  const selAtmosphere = atmosphere?.stations.find(s => s.station === selected) ?? atmosphere?.stations[0] ?? null
  const windDir = transport?.dominant_wind_direction as Record<string, unknown> | undefined
  const modelLabels: Record<string, string> = { persistence: 'Persistence', random_forest: 'Random Forest', xgboost: 'XGBoost', gru: 'GRU' }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">AeroCast-NCR Command Dashboard</h1>
          <p className="text-sm text-gray-400">Delhi NCR · real observations + 72-h model forecast</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer select-none">
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} className="accent-blue-500" />
            Auto-refresh (1 min)
          </label>
          <select value={selected} onChange={e => setSelected(e.target.value)} className="bg-navy-800 border border-navy-700 rounded-lg px-4 py-2 text-sm">
            {stations.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
            {!stations.length && <option>Anand Vihar</option>}
          </select>
        </div>
      </div>

      {/* Provenance legend */}
      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
        <span className="font-semibold text-gray-300 mr-1">Data provenance:</span>
        <ProvenanceChip label="OBSERVED" />
        <ProvenanceChip label="DERIVED" />
        <ProvenanceChip label="ESTIMATED" />
        <ProvenanceChip label="FORECAST" />
        <ProvenanceChip label="SCENARIO" />
        <ProvenanceChip label="MEASURED" />
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm flex items-center justify-between gap-3">
          <span>{error}</span>
          <button onClick={() => refreshAll()} className="bg-red-700 hover:bg-red-600 rounded px-3 py-1 text-xs whitespace-nowrap">Retry</button>
        </div>
      )}

      {loading && <div className="text-center py-12 text-gray-400">Loading dashboard…</div>}

      {/* ============ 1. CURRENT AIR QUALITY ============ */}
      <section className="card">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <SectionTitle icon="📊" title="Current Air Quality" chips={['OBSERVED']} />
          <div className="flex items-center gap-2">
            {current?.aqi_category && <AQIBadge category={current.aqi_category} aqi={current.aqi} />}
            <span className="text-xs text-gray-500">as of {tsFmt(current?.timestamp)}Z</span>
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <AQICard label="AQI" value={current?.aqi} />
          <AQICard label="PM2.5" value={current?.pm25} unit="μg/m³" />
          <AQICard label="PM10" value={current?.pm10} unit="μg/m³" />
          <AQICard label="O₃" value={current?.o3} unit="μg/m³" />
          <AQICard label="NO₂" value={current?.no2} unit="μg/m³" />
          <AQICard label="SO₂" value={current?.so2} unit="μg/m³" />
        </div>
        <p className="text-xs text-gray-500 mt-3">
          {current ? `Dominant pollutant: ${current.dominant_pollutant ?? '—'} · CPCB live network.` : 'No observed readings yet — run CPCB ingestion once a data.gov.in key is configured.'}
        </p>
      </section>

      {/* ============ 2. 72-HOUR FORECAST ============ */}
      <section className="card">
        <SectionTitle icon="📈" title="72-Hour Forecast" chips={['FORECAST']} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-4">
          <div>
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-sm font-medium text-gray-300">Hourly PM2.5 forecast + uncertainty</h3>
              {pm25 && <span className="text-xs text-gray-500">{pm25.uncertainty_method} · {pm25.forecast_strategy}</span>}
            </div>
            {pm25 ? (
              <>
                <Pm25ForecastChart data={pm25.forecasts} observed={current?.pm25 ?? null} />
                <p className="text-xs text-gray-500 mt-1">
                  Shaded band = per-horizon conformal prediction range ({pm25.coverage_target ? `${Math.round(pm25.coverage_target * 100)}% coverage` : 'calibrated coverage'}). Released at {tsFmt(pm25.release_time)}Z.
                </p>
              </>
            ) : (
              <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-6 text-sm text-gray-400">
                PM2.5 forecast engine not available. Run <code className="text-amber-300">python -m ml.training.train_pm25 --horizons "1..72"</code> then retry.
              </div>
            )}
          </div>
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-1">AQI forecast (persisted)</h3>
            {forecast.length ? <ForecastChart data={forecast} pollutant="aqi_pred" color="#3b82f6" /> : <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-6 text-sm text-gray-400">No persisted AQI forecast for this station yet.</div>}
          </div>
        </div>
      </section>

      {/* ============ 3. ATMOSPHERIC CONDITIONS ============ */}
      <section className="card">
        <SectionTitle icon="🌬️" title="Atmospheric Conditions" chips={['OBSERVED', 'DERIVED', 'ESTIMATED']} />
        {selAtmosphere ? (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mt-4">
            <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-3">
              <div className="flex items-center justify-between"><p className="text-xs text-gray-400">Wind</p><ProvenanceChip label={selAtmosphere.wind.provenance} /></div>
              <p className="text-xl font-bold mt-1">
                {fmt(selAtmosphere.wind.wind_speed_mps, 1)} <span className="text-xs text-gray-400">m/s</span>
              </p>
              <p className="text-xs text-gray-400 mt-0.5">
                {selAtmosphere.wind.compass_from ?? '--'} · {selAtmosphere.wind.label}
              </p>
            </div>
            <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-3">
              <div className="flex items-center justify-between"><p className="text-xs text-gray-400">PBL Height</p><ProvenanceChip label={selAtmosphere.pbl.provenance} /></div>
              <p className="text-xl font-bold mt-1">{fmt(selAtmosphere.pbl.pbl_height_m)} <span className="text-xs text-gray-400">m</span></p>
              <p className="text-xs text-gray-400 mt-0.5">{selAtmosphere.pbl.label}</p>
            </div>
            <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-3">
              <div className="flex items-center justify-between"><p className="text-xs text-gray-400">Ventilation</p><ProvenanceChip label={selAtmosphere.ventilation.provenance} /></div>
              <p className="text-xl font-bold mt-1">{fmt(selAtmosphere.ventilation.ventilation_coefficient_m2s)} <span className="text-xs text-gray-400">m²/s</span></p>
              <p className="text-xs text-gray-400 mt-0.5">{selAtmosphere.ventilation.label}</p>
            </div>
            <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-gray-400">Inversion</p>
                <ProvenanceChip label={selAtmosphere.inversion?.provenance ?? 'ESTIMATED'} />
              </div>
              <p className="text-xl font-bold mt-1">{selAtmosphere.inversion?.detected ? selAtmosphere.inversion.category : 'None'}</p>
              <p className="text-xs text-gray-400 mt-0.5">
                {selAtmosphere.inversion?.strongest_gradient_k100hpa != null ? `${fmt(selAtmosphere.inversion.strongest_gradient_k100hpa, 2)} K/100hPa` : 'No lapse-rate profile'}
              </p>
            </div>
            <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-3">
              <div className="flex items-center justify-between"><p className="text-xs text-gray-400">Trapping risk</p><ProvenanceChip label={selAtmosphere.trapping.provenance} /></div>
              <p className="text-xl font-bold mt-1">{fmt(selAtmosphere.trapping.score, 2)}</p>
              <p className="text-xs text-gray-400 mt-0.5">{selAtmosphere.trapping.label}</p>
            </div>
          </div>
        ) : (
          <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-6 text-sm text-gray-400 mt-4">
            No atmospheric profile available yet (needs stored weather + pressure-level data).
          </div>
        )}
      </section>

      {/* ============ 4. REGIONAL FIRE INTELLIGENCE ============ */}
      <section className="card">
        <SectionTitle icon="🔥" title="Regional Fire Intelligence & Transport Risk" chips={['OBSERVED', 'ESTIMATED']} />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-4">
          <div className="lg:col-span-2">
            <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-gray-300">Transport risk (region)</p>
                <span className={`text-lg font-bold ${transport?.risk_level === 'HIGH' ? 'text-red-400' : transport?.risk_level === 'MODERATE' ? 'text-amber-400' : 'text-green-400'}`}>
                  {transport?.risk_level ?? '--'}
                </span>
              </div>
              <div className="mt-2 h-3 w-full rounded-full bg-navy-700">
                <div className="h-3 rounded-full bg-gradient-to-r from-green-500 via-amber-500 to-red-500 transition-all"
                  style={{ width: `${Math.max(0, Math.min(100, transport?.risk_score ?? 0))}%` }} />
              </div>
              <p className="text-xs text-gray-500 mt-1">0–100 ({fmt(transport?.risk_score, 0)} current) · ESTIMATED from FIRMS + regional winds, not a plume model.</p>
              {transport?.main_contributing_factors?.length ? (
                <ul className="mt-2 space-y-1 text-xs text-gray-400">
                  {transport.main_contributing_factors.slice(0, 4).map((f, i) => <li key={i}>• {f}</li>)}
                </ul>
              ) : null}
            </div>
            <p className="text-xs text-gray-500 mt-3">{transport?.disclaimer}</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-3">
              <p className="text-xs text-gray-400">Hotspots (24 h)</p>
              <p className="text-xl font-bold">{fireActivity?.total_fires ?? hotspots.length}</p>
            </div>
            <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-3">
              <p className="text-xs text-gray-400">Upwind in transport estimate</p>
              <p className="text-xl font-bold">{transport?.upwind_fire_count ?? '--'}</p>
            </div>
            <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-3">
              <p className="text-xs text-gray-400">Mean FRP</p>
              <p className="text-xl font-bold">{fmt(fireActivity?.mean_frp, 1)} <span className="text-xs text-gray-400">MW</span></p>
            </div>
            <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-3">
              <p className="text-xs text-gray-400">Dominant wind</p>
              <p className="text-xl font-bold">{String(windDir?.compass_from ?? '--')}</p>
              <p className="text-xs text-gray-400 mt-0.5">{String(windDir?.wind_speed_mps ?? '')} m/s</p>
            </div>
          </div>
        </div>
      </section>

      {/* ============ 5. EXPLAINABILITY ============ */}
      <section className="card">
        <SectionTitle icon="🧠" title="Explainability — Why is it expected to change?" chips={['MODEL', 'DERIVED']} />
        <div className="mt-4">
          {explanation ? (
            <ExplainabilityPanel data={explanation} />
          ) : (
            <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-6 text-sm text-gray-400">
              No model explanation available for this station yet.
            </div>
          )}
        </div>
      </section>

      {/* ============ 6. MODEL PERFORMANCE ============ */}
      <section className="card">
        <SectionTitle icon="🎯" title="Model Performance (held-out test set)" chips={['MEASURED']} />
        {modelPerf?.results?.length ? (
          <>
            <div className="overflow-x-auto mt-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-400 border-b border-navy-700">
                    <th className="text-left py-2">Horizon</th>
                    {modelPerf.evaluated_models.map(m => (
                      <th key={m} className="text-left py-2 px-2">{modelLabels[m] ?? m}</th>
                    ))}
                    <th className="text-right py-2">N (test)</th>
                  </tr>
                </thead>
                <tbody>
                  {modelPerf.results.map(r => (
                    <tr key={r.horizon_hours} className="border-b border-navy-700/50">
                      <td className="py-2 font-medium">+{r.horizon_hours}h</td>
                      {modelPerf.evaluated_models.map(m => {
                        const mm = r.metrics[m]
                        return (
                          <td key={m} className="py-2 px-2 text-xs">
                            MAE {fmt(mm?.mae, 1)} · RMSE {fmt(mm?.rmse, 1)} · R² {fmt(mm?.r2, 2)}
                          </td>
                        )
                      })}
                      <td className="text-right py-2">{r.n_test?.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-gray-500 mt-3">
              Target: {modelPerf.target ?? 'pm25'} · split {modelPerf.split_type} · measured {tsFmt(modelPerf.generated_at)}. R² closer to 1 = better; MAE/RMSE in μg/m³.
            </p>
          </>
        ) : (
          <div className="rounded-lg border border-navy-700 bg-navy-900/40 p-6 text-sm text-gray-400 mt-4">
            No measured metrics yet — run <code className="text-amber-300">python -m ml.training.evaluate_pm25</code>.
          </div>
        )}
      </section>

      {/* ============ 7. MAP ============ */}
      <section className="card p-0 overflow-hidden">
        <div className="p-6 pb-0">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <SectionTitle icon="🗺️" title="NCR Station Map" chips={['OBSERVED', 'ESTIMATED']} />
            <span className="text-xs text-gray-500">stations = AQI color · circles = FIRMS hotspots (FRP size/color) · cyan arrows = wind (flow direction)</span>
          </div>
        </div>
{stations.length ? (
          <StationMap
            stations={stations}
            pollution={pollution}
            fires={hotspots}
            wind={buildWindArrows(stations, atmosphere)}
          />
        ) : (
          <div className="p-6 text-sm text-gray-400">No stations loaded.</div>
        )}
      </section>

      <footer className="pb-4 text-center text-xs text-gray-600">
        AeroCast-NCR · SIH26082 (MoES / NCMRWF) · all provenance labels are per endpoint data, no fabricated values
      </footer>
    </div>
  )
}