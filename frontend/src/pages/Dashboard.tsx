import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  Flame,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import {
  getStations,
  getCurrentAQI,
  getForecast,
  getPm25Forecast,
  getAtmosphereCurrent,
  getFireActivity,
  getFireHotspots,
  getTransportRisk,
  getModelPerformance,
  getPollutionLatest,
  getPollutionHistory,
  getGrapCurrent,
  getSummary,
  getAlerts,
} from '../api/client'
import PageHeader from '../components/PageHeader'
import AQIBadge from '../components/AQIBadge'
import LoadingState from '../components/LoadingState'
import ErrorState from '../components/ErrorState'
import EmptyState from '../components/EmptyState'
import StationMap from '../components/StationMap'
import AtmosphericState from '../components/AtmosphericState'
import AtmosphericStory from '../components/AtmosphericStory'
import DispersionMeter from '../components/DispersionMeter'
import ForecastRiskBand from '../components/ForecastRiskBand'
import TransportChain from '../components/TransportChain'
import AlertsSection from '../components/AlertsSection'
import ForecastReasonPanel from '../components/ForecastReasonPanel'
import { useIntervalRefresh } from '../hooks/useIntervalRefresh'
import { aqiStyle, fmt, tsFmt } from '../lib/aqi'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type {
  Station, CurrentAQI, ForecastPoint, Pm25ForecastResponse, Pm25ForecastPoint,
  AtmosphereCurrentResponse, FireActivity, FireHotspot, TransportRiskResponse,
  ModelPerformanceResponse, PollutionReading, Alert, SummaryResponse, GrapAssessment,
} from '../types'

interface WindVectorInput {
  lat: number
  lon: number
  direction_deg: number | null
  speed: number | null
}

function buildWindArrows(stations: Station[], atmosphere: AtmosphereCurrentResponse | null): WindVectorInput[] {
  if (!atmosphere) return []
  const out: WindVectorInput[] = []
  for (const st of stations) {
    const a = atmosphere.stations.find((x) => x.station === st.name)
    if (a && a.wind?.wind_direction_deg != null) {
      out.push({
        lat: st.latitude,
        lon: st.longitude,
        direction_deg: a.wind.wind_direction_deg,
        speed: a.wind.wind_speed_mps,
      })
    }
  }
  return out
}

function ChartTooltip() {
  return { contentStyle: { backgroundColor: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8 }, labelStyle: { color: '#334155' } }
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
  const [grap, setGrap] = useState<GrapAssessment | null>(null)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [modelPerf, setModelPerf] = useState<ModelPerformanceResponse | null>(null)
  const [pollution, setPollution] = useState<PollutionReading[]>([])
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)

  useEffect(() => {
    getStations()
      .then((r) => setStations(r.data))
      .catch(() => setStations([]))
  }, [])

  const refreshAll = useCallback(() => {
    setError(null)
    return Promise.allSettled([
      getSummary().then((r) => setSummary(r.data)).catch(() => {}),
      getCurrentAQI(selected).then((r) => setCurrent(r.data)).catch(() => setCurrent(null)),
      getForecast(selected).then((r) => setForecast(r.data)).catch(() => setForecast([])),
      getPm25Forecast(selected)
        .then((r) => setPm25(r.data))
        .catch(() => setPm25(null)),
      getAtmosphereCurrent(selected).then((r) => setAtmosphere(r.data)).catch(() => setAtmosphere(null)),
      getFireActivity().then((r) => setFireActivity(r.data)).catch(() => setFireActivity(null)),
      getFireHotspots()
        .then((r) => setHotspots(r.data.hotspots))
        .catch(() => setHotspots([])),
      getTransportRisk().then((r) => setTransport(r.data)).catch(() => setTransport(null)),
      getModelPerformance().then((r) => setModelPerf(r.data)).catch(() => setModelPerf(null)),
      getPollutionLatest().then((r) => setPollution(r.data)).catch(() => setPollution([])),
      getGrapCurrent().then((r) => setGrap(r.data)).catch(() => setGrap(null)),
      getAlerts().then((r) => setAlerts(r.data)).catch(() => setAlerts([])),
    ]).then()
  }, [selected])

  useEffect(() => {
    setLoading(true)
    refreshAll().finally(() => setLoading(false))
  }, [refreshAll])

  useIntervalRefresh(refreshAll, 60_000, autoRefresh)

  const modelLabels: Record<string, string> = {
    persistence: 'Persistence',
    random_forest: 'Random Forest',
    xgboost: 'XGBoost',
    gru: 'GRU',
  }

  const rankStyle = aqiStyle(current?.aqi ?? null)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Atmospheric Intelligence Control Room"
        subtitle="Delhi NCR · one consolidated view of live CPCB observations, 72-hour ML forecasts, atmospheric physics and regional fire-plume transport"
        breadcrumbs={[{ label: 'Control Room' }]}
        lastUpdated={summary?.generated_at ?? current?.timestamp}
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <label className="inline-flex cursor-pointer select-none items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="h-3.5 w-3.5 accent-inst-700"
              />
              Auto-refresh (1 min)
            </label>
            <select value={selected} onChange={(e) => setSelected(e.target.value)} className="select" aria-label="Select monitoring station">
              {stations.map((s) => (
                <option key={s.id} value={s.name}>{s.name}</option>
              ))}
            </select>
          </div>
        }
      />

      {error && (
        <ErrorState
          title="Control room is unavailable"
          message="The API server could not be reached. Verify the backend is running on :8000."
          onRetry={() => {
            setLoading(true)
            refreshAll().finally(() => setLoading(false))
          }}
        />
      )}

      {loading && !current && !summary ? (
        <LoadingState label="Loading control room" rows={3} />
      ) : (
        <>
          {/* ---------- Regional pulse ---------- */}
          {summary && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <div className="card flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-inst-50">
                  <Sparkles className="h-5 w-5 text-inst-700" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-xs text-slate-500">NCR average AQI</p>
                  <div className="flex items-center gap-2">
                    <p className="text-xl font-bold text-slate-900">{fmt(summary.ncr_avg_aqi, 0)}</p>
                    <AQIBadge category={aqiStyle(summary.ncr_avg_aqi).label} aqi={summary.ncr_avg_aqi} />
                  </div>
                </div>
              </div>

              <StationRank summary={summary} best />
              <StationRank summary={summary} />

              <div className="card flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-orange-50">
                  <Flame className="h-5 w-5 text-orange-600" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-xs text-slate-500">Active fires (24 h)</p>
                  <p className="text-xl font-bold text-slate-900">{summary.active_fires_24h}</p>
                </div>
              </div>

              <div className="card flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-50">
                  <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-xs text-slate-500">Open alerts</p>
                  <p className="text-xl font-bold text-slate-900">{summary.open_alerts}</p>
                </div>
              </div>
            </div>
          )}

          {/* ---------- Station grid ---------- */}
          <div>
            <h2 className="mb-3 text-base font-semibold text-slate-900">Monitoring stations</h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6 xl:grid-cols-6">
              {stations.map((s) => {
                const r = pollution.find((p) => p.station_id === s.id)
                const style = aqiStyle(r?.aqi ?? null)
                const isSel = s.name === selected
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setSelected(s.name)}
                    aria-pressed={isSel}
                    className={`rounded-xl border bg-white p-3 text-left shadow-card transition-all ${
                      isSel ? 'border-inst-600 ring-2 ring-inst-200' : 'border-slate-200 hover:border-inst-300'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <p className="truncate text-xs font-semibold text-slate-800">{s.name}</p>
                      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${style.bar}`} aria-hidden="true" />
                    </div>
                    <p className="mt-1 text-lg font-bold tabular-nums text-slate-900">
                      {fmt(r?.aqi ?? null, 0)}
                      <span className="ml-1 text-[10px] font-normal text-slate-400">AQI</span>
                    </p>
                    <p className="truncate text-[10px] text-slate-500">
                      PM2.5 {fmt(r?.pm25 ?? null, 0)}<span className="text-slate-400"> μg/m³</span>
                    </p>
                    {r ? (
                      <p className="truncate text-[10px] font-medium capitalize text-slate-600">{style.label}</p>
                    ) : (
                      <p className="truncate text-[10px] italic text-slate-400">Awaiting live data</p>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          {/* ---------- Station banner ---------- */}
          <div className="grid gap-6 lg:grid-cols-3">
            <section className="card lg:col-span-1">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-base font-bold text-slate-900">{selected}</h2>
                  <p className="text-xs text-slate-500">
                    {stations.find((s) => s.name === selected)?.city ?? 'Delhi NCR'} · updated {tsFmt(current?.timestamp)}
                  </p>
                </div>
                {current && <AQIBadge category={current.aqi_category} aqi={current.aqi} />}
              </div>

              <div className="mt-3 flex items-center gap-3">
                <div className={`flex h-16 w-16 shrink-0 flex-col items-center justify-center rounded-xl text-white ${rankStyle.bar}`}>
                  <span className="text-2xl font-bold leading-none tabular-nums">{fmt(current?.aqi, 0)}</span>
                  <span className="text-[10px] font-medium uppercase">AQI</span>
                </div>
                <div className="min-w-0">
                  <p className={`text-sm font-semibold capitalize ${rankStyle.text}`}>{rankStyle.label}</p>
                  <p className="truncate text-xs text-slate-500">
                    Dominant: {current?.dominant_pollutant ?? '—'}
                  </p>
                  <p className="text-xs text-slate-500">{tsFmt(current?.timestamp)} UTC</p>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2">
                {[
                  { label: 'PM2.5', v: current?.pm25 },
                  { label: 'PM10', v: current?.pm10 },
                  { label: 'O₃', v: current?.o3 },
                  { label: 'NO₂', v: current?.no2 },
                ].map((p) => (
                  <div key={p.label} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                    <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{p.label}</p>
                    <p className="text-base font-bold tabular-nums text-slate-900">{fmt(p.v, 1)}</p>
                  </div>
                ))}
              </div>

              {!current && (
                <p className="mt-3 text-xs leading-relaxed text-slate-500">
                  No CPCB readings have been published for this station yet — the PMC uses NWP data for its
                  forecast until live observations arrive.
                </p>
              )}
            </section>

            <div className="lg:col-span-2">
              <AtmosphericState atmosphere={atmosphere?.stations.find((s) => s.station === selected) ?? null} />
            </div>
          </div>

          {/* ---------- Atmospheric narrative + dispersion ---------- */}
          <div className="grid gap-6 lg:grid-cols-2">
            <AtmosphericStory atmosphere={atmosphere?.stations.find((s) => s.station === selected) ?? null} />
            <DispersionMeter atmosphere={atmosphere?.stations.find((s) => s.station === selected) ?? null} />
          </div>

          {/* ---------- 72-hour outlook ---------- */}
          <div className="grid gap-6 lg:grid-cols-2">
            <ForecastRiskBand forecast={forecast} />
            <section className="card">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-bold text-slate-900">72-hour PM2.5 forecast — {selected}</h2>
                {pm25 && <span className="text-xs text-slate-500">{pm25.uncertainty_method} · {pm25.forecast_strategy}</span>}
                <Link to="/forecast" className="text-xs font-semibold text-inst-700 hover:underline">
                  Open full forecast →
                </Link>
              </div>
              <ForecastPreview point={pm25?.forecasts?.slice(0, 24) ?? forecast.slice(0, 24)} observed={current?.pm25 ?? null} />
            </section>
          </div>

          {/* ---------- Why this forecast ---------- */}
          <ForecastReasonPanel station={selected} />

          {/* ---------- Regional transport ---------- */}
          <TransportChain transport={transport} fire={fireActivity} />

          {/* ---------- Alerts strip ---------- */}
          <AlertsSection alerts={alerts} grap={grap} />

          {/* ---------- Model performance summary ---------- */}
          <section className="card">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-bold text-slate-900">Forecast model quality</h2>
              <Link to="/model-performance" className="text-xs font-semibold text-inst-700 hover:underline">
                Full metrics →
              </Link>
            </div>
            {modelPerf?.results?.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500">
                      <th className="py-2 text-left">Horizon</th>
                      {modelPerf.evaluated_models.map((m) => (
                        <th key={m} className="px-2 py-2 text-left">{modelLabels[m] ?? m}</th>
                      ))}
                      <th className="py-2 text-right">N (test)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {modelPerf.results.slice(0, 12).map((r) => (
                      <tr key={r.horizon_hours} className="border-b border-slate-100">
                        <td className="py-2 font-semibold text-slate-900">+{r.horizon_hours}h</td>
                        {modelPerf.evaluated_models.map((m) => {
                          const mm = r.metrics[m]
                          return (
                            <td key={m} className="px-2 py-2 text-xs text-slate-700">
                              MAE {fmt(mm?.mae, 1)} · R² {fmt(mm?.r2, 2)}
                            </td>
                          )
                        })}
                        <td className="py-2 text-right text-slate-700">{r.n_test?.toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-slate-500">No measured metrics available yet.</p>
            )}
          </section>

          {/* ---------- Map ---------- */}
          <section className="card overflow-hidden p-0">
            <div className="px-6 pt-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-bold text-slate-900">NCR monitoring map</h2>
                <span className="text-xs text-slate-500">stations = AQI colour · circles = FIRMS hotspots · cyan arrows = wind</span>
              </div>
            </div>
            <div className="p-3">
              {stations.length ? (
                <StationMap
                  stations={stations}
                  pollution={pollution}
                  fires={hotspots}
                  wind={buildWindArrows(stations, atmosphere)}
                  onSelectStation={setSelected}
                />
              ) : (
                <EmptyState title="No stations loaded" />
              )}
            </div>
          </section>
        </>
      )}
    </div>
  )
}

function StationRank({ summary, best = false }: { summary: SummaryResponse; best?: boolean }) {
  const target = best ? summary.best_station : summary.worst_station
  if (!target || target.aqi == null) return <div className="card" />
  const style = aqiStyle(target.aqi)
  const Icon = best ? TrendingDown : TrendingUp
  return (
    <div className="card flex items-center gap-3">
      <span className={`flex h-10 w-10 items-center justify-center rounded-lg ${best ? 'bg-green-50' : 'bg-red-50'}`}>
        <Icon className={`h-5 w-5 ${best ? 'text-green-600' : 'text-red-600'}`} aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="text-xs text-slate-500">{best ? 'Cleanest station' : 'Most polluted'}</p>
        <p className="truncate text-sm font-bold text-slate-900">{target.name}</p>
        <p className={`text-xs font-semibold capitalize ${style.text}`}>{style.label} · {fmt(target.aqi, 0)}</p>
      </div>
    </div>
  )
}

function ForecastPreview({ point, observed }: { point: Pm25ForecastPoint[] | ForecastPoint[]; observed: number | null }) {
  if (!point.length) {
    return (
      <EmptyState
        title="Forecast engine not available"
        hint="Train the PM2.5 horizon models to populate the 72-hour forecast chart."
      />
    )
  }
  const rows = point.map((p) => {
    const pm = p as Partial<Pm25ForecastPoint>
    const fc = p as Partial<ForecastPoint>
    const isPm25 = typeof pm.predicted_pm25 === 'number'
    return {
      time: `+${pm.forecast_horizon ?? fc.horizon_hours ?? 0}h`,
      pred: isPm25 ? (pm.predicted_pm25 ?? 0) : (fc.pm25_pred ?? fc.aqi_pred ?? 0),
    }
  })
  if (observed !== null && observed !== undefined) {
    rows.unshift({ time: 'now', pred: observed })
  }
  const tooltip = ChartTooltip()
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={rows} margin={{ left: -20, right: 8 }}>
        <defs>
          <linearGradient id="fcastFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#1d5f9c" stopOpacity={0.28} />
            <stop offset="95%" stopColor="#1d5f9c" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
        <YAxis stroke="#64748b" fontSize={11} />
        <Tooltip {...tooltip} />
        <ReferenceLine y={60} stroke="#d97706" strokeDasharray="4 4" label={{ value: 'NAAQS 60', position: 'insideTopRight', fill: '#d97706', fontSize: 10 }} />
        <Area type="monotone" dataKey="pred" stroke="#1d5f9c" strokeWidth={2} fill="url(#fcastFill)" name="PM2.5 (μg/m³)" />
      </AreaChart>
    </ResponsiveContainer>
  )
}