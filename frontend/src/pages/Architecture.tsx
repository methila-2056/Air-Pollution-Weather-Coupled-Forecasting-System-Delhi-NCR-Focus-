import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Cloud,
  Database,
  GitMerge,
  LayoutGrid,
  Map,
  Network,
  ShieldCheck,
  Zap,
} from 'lucide-react'
import { getSystemStatus, getModelPerformance } from '../api/client'
import PageHeader from '../components/PageHeader'
import LoadingState from '../components/LoadingState'
import ErrorState from '../components/ErrorState'
import { useIntervalRefresh } from '../hooks/useIntervalRefresh'
import { tsFmt } from '../lib/aqi'
import type { SystemResponse, ModelPerformanceResponse } from '../types'

const statusStyle: Record<string, string> = {
  active: 'border-emerald-300 bg-emerald-50 text-emerald-700',
  usable: 'border-emerald-300 bg-emerald-50 text-emerald-700',
  available: 'border-emerald-300 bg-emerald-50 text-emerald-700',
  configured: 'border-emerald-300 bg-emerald-50 text-emerald-700',
  connected: 'border-emerald-300 bg-emerald-50 text-emerald-700',
  surrogate: 'border-indigo-300 bg-indigo-50 text-indigo-700',
  archive: 'border-indigo-300 bg-indigo-50 text-indigo-700',
  gated: 'border-amber-300 bg-amber-50 text-amber-700',
  'not-configured': 'border-slate-300 bg-slate-100 text-slate-600',
}

const stageOrder: Record<string, number> = {
  weather_forecast: 0,
  cpcb: 1,
  firms: 2,
  imd: 3,
  ctm_hysplit: 4,
  ctm_wrf_chem: 5,
}

const engineLabels: Record<string, string> = {
  weather_forecast: 'Weather forecast engine',
  cpcb: 'CPCB live AQ feed',
  firms: 'NASA FIRMS fires',
  imd: 'IMD official weather',
  ctm_hysplit: 'HYSPLIT transport',
  ctm_wrf_chem: 'WRF-Chem CTM surface',
}

const pipeline = [
  {
    stage: 'Ingest · 6 channels',
    items: ['CPCB / data.gov.in (AQI)', 'NASA FIRMS VIIRS (fires)', 'Open-Meteo (vertical p-levels)', 'IMD (gated)', 'ERA5 (gated)', 'WRF-Chem wrfout surface (gated)'],
  },
  {
    stage: 'Normalise & store',
    items: ['18 CPCB NCR stations', 'Pollution readings', 'Weather + vertical profile', 'Fire detections (FRP)', 'Persisted in Neon PostgreSQL'],
  },
  {
    stage: 'Coupling & features',
    items: ['Two-way aerosol–PBL coupling', 'Inversion / lapse-rate score', 'Ventilation & dispersion', 'Fire-plume transport & PM2.5 impact'],
  },
  {
    stage: 'Prediction engine',
    items: ['XGBoost · Random Forest · GRU', '4 pollutants × 6 horizons (1–72h)', 'Split-conformal intervals', 'SHAP explainability', 'Verified skill shown on the Model Performance page (chronological split)'],
  },
  {
    stage: 'Forecast services',
    items: ['72h per-station & NCR outlook', 'Spatial grid outlook', 'Pollution events (surges/episodes)', 'Scenario analysis', 'Alerts + CAQM GRAP stages'],
  },
  {
    stage: 'Consumers',
    items: ['Operational dashboard', 'GRADED RESPONSE ACTION PLAN', 'CPCB / DPCC action desk', 'Public & media briefings'],
  },
]

export default function ArchitecturePage() {
  const [sys, setSys] = useState<SystemResponse | null>(null)
  const [modelPerf, setModelPerf] = useState<ModelPerformanceResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    getSystemStatus()
      .then((r) => {
        setSys(r.data)
        setError(null)
      })
      .catch((e) => setError(e?.message ?? 'Failed to load system status'))
    getModelPerformance('pm25')
      .then((r) => setModelPerf(r.data))
      .catch(() => setModelPerf(null))
  }

  useEffect(() => { load() }, [])
  useIntervalRefresh(load, 60_000, false)

  if (error && !sys) return <ErrorState title="System status unavailable" message={error} onRetry={load} />
  if (!sys) return <LoadingState label="Loading architecture & engine status…" />

  const engines = Object.entries(sys.engines)
    .sort(([a], [b]) => (stageOrder[a] ?? 99) - (stageOrder[b] ?? 99))

  return (
    <div>
      <PageHeader
        title="Architecture & system status"
        subtitle="How AeroCast-NCR couples pollution and weather data into a 72-hour operational forecast for Delhi NCR (SIH26082)."
        breadcrumbs={[{ label: 'Tools' }, { label: 'Architecture & system status' }]}
        lastUpdated={sys.generated_at}
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="card flex items-center gap-3">
          <Database className="h-6 w-6 text-inst-700" aria-hidden="true" />
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Database</p>
            <p className={`text-sm font-bold ${sys.database === 'connected' ? 'text-emerald-700' : 'text-red-600'}`}>
              {sys.database === 'connected' ? 'Neon PostgreSQL connected' : sys.database}
            </p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <Zap className="h-6 w-6 text-inst-700" aria-hidden="true" />
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Run mode</p>
            <p className="text-sm font-bold text-slate-900">
              {sys.run_mode.live_refresh_enabled ? 'Live-refresh scheduler ON' : 'Scheduled refresh off'}
            </p>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <ShieldCheck className="h-6 w-6 text-inst-700" aria-hidden="true" />
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Honesty mode</p>
            <p className="text-sm font-bold text-slate-900">
              {sys.run_mode.demo_hydrate_empty_db ? 'Demo-seeded (re-stamped archive)' : 'Verbatim archive'}
            </p>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-6">
        <section className="card">
          <div className="mb-3 flex items-center gap-2">
            <Network className="h-5 w-5 text-inst-700" aria-hidden="true" />
            <h2 className="text-base font-bold text-slate-900">Data → prediction pipeline</h2>
          </div>
          <div className="flex flex-wrap gap-3">
            {pipeline.map((p, i) => (
              <div key={p.stage} className="flex flex-col sm:min-w-[220px] sm:flex-1">
                <div className="relative rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-inst-700">
                    {[<Cloud key="a" className="h-3.5 w-3.5" aria-hidden="true" />, <GitMerge key="g" className="h-3.5 w-3.5" aria-hidden="true" />, <LayoutGrid key="l" className="h-3.5 w-3.5" aria-hidden="true" />, <Zap key="z" className="h-3.5 w-3.5" aria-hidden="true" />, <Map key="m" className="h-3.5 w-3.5" aria-hidden="true" />, <Database key="d" className="h-3.5 w-3.5" aria-hidden="true" />][i]}
                    {p.stage}
                  </p>
                  <ul className="space-y-1">
                    {p.items.map((it) => (
                      <li key={it} className="text-xs text-slate-600">{it}</li>
                    ))}
                  </ul>
                </div>
                {i < pipeline.length - 1 && (
                  <span className="mx-auto flex h-6 items-center text-slate-300" aria-hidden="true">↓</span>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className="card">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Network className="h-5 w-5 text-inst-700" aria-hidden="true" />
              <h2 className="text-base font-bold text-slate-900">External engines & integrations — live status</h2>
            </div>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-500">
              <span className="font-semibold text-emerald-700">green</span> real & wired ·{' '}
              <span className="font-semibold text-indigo-700">indigo</span> archive/surrogate ·{' '}
              <span className="font-semibold text-amber-700">amber</span> gated/needs key
            </span>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {engines.map(([key, e]) => (
              <div key={key} className="rounded-xl border border-slate-200 p-4">
                <div className="mb-1 flex items-start justify-between gap-2">
                  <p className="text-sm font-bold text-slate-900">{engineLabels[key] ?? key}</p>
                  <span className={`shrink-0 rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${statusStyle[e.status] ?? statusStyle['not-configured']}`}>
                    {e.status.replace('-', ' ')}
                  </span>
                </div>
                <p className="text-xs text-slate-500">{e.source}</p>
                <p className="mt-2 text-xs leading-relaxed text-slate-600">{e.note}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="card">
          <h2 className="mb-2 text-base font-bold text-slate-900">What is honest here</h2>
          <p className="text-sm text-slate-600">{sys.run_mode.explanation}</p>
          <p className="mt-2 text-sm text-slate-600">
            All ML metrics shown anywhere in this product come from a chronological train/test split on persisted
            observations — never synthetic. Engines marked <span className="font-semibold text-amber-700">gated</span> or{' '}
            <span className="font-semibold text-indigo-700">surrogate</span> are reported as they are: WRF-Chem absorbs only real{' '}
            <span className="font-mono text-xs">wrfout_d01_*.nc</span> files, HYSPLIT only runs when a real install + met files exist,
            and IMD returns 401 without its registration key. Impossible-to-claim accuracy is never claimed.
          </p>
          <p className="mt-2 text-xs text-slate-500">
            Verified model skill is always read from the persisted chronological train/test split — never synthetic.
            {(() => {
              const pick = (h: number) => modelPerf?.results.find((r) => r.horizon_hours === h)?.metrics?.xgboost
              const h1 = pick(1)
              const h24 = pick(24)
              const h72 = pick(72)
              if (h1 && h24 && h72) {
                return (
                  <>
                    {' '}PM2.5 XGBoost on split {String(modelPerf?.split_type ?? '')}: +1h R² {h1.r2?.toFixed(2) ?? '--'} (MAE {h1.mae?.toFixed(1) ?? '--'}), +24h R² {h24.r2?.toFixed(2) ?? '--'} (MAE {h24.mae?.toFixed(1) ?? '--'}), +72h R² {h72.r2?.toFixed(2) ?? '--'} (MAE {h72.mae?.toFixed(1) ?? '--'}).
                  </>
                )
              }
              return <> Full metrics (per model, pollutant and horizon) are shown on the <Link to="/model-performance" className="font-semibold text-inst-700 hover:underline">Model Performance</Link> page.</>
            })()}{' '}
            Last checked {tsFmt(sys.generated_at)}.
          </p>
        </section>
      </div>
    </div>
  )
}