import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Cell,
} from 'recharts'
import { FlaskConical, Info, ShieldCheck } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import LoadingState from '../components/LoadingState'
import ErrorState from '../components/ErrorState'
import EmptyState from '../components/EmptyState'
import { getStations, postScenarioAnalysis } from '../api/client'
import type { Station, ScenarioAnalysisResponse, ScenarioChangesInput } from '../types'
import { CHART } from '../lib/theme'

const tooltipStyle = {
  contentStyle: { backgroundColor: CHART.tooltipBg, border: `1px solid ${CHART.tooltipBorder}`, borderRadius: 8 },
  labelStyle: { color: CHART.tooltipLabel },
}

function fmt(v: number | null | undefined, digits = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return v.toFixed(digits)
}

function hourLabel(h: number) {
  if (h === 0) return 'Now'
  return `+${h}h`
}

interface ControlProps {
  label: string
  hint: string
  children: ReactNode
}

function Control({ label, hint, children }: ControlProps) {
  return (
    <label className="block rounded-xl border border-slate-200 bg-white p-3">
      <span className="text-sm font-semibold text-slate-800">{label}</span>
      <span className="block text-[11px] text-slate-500">{hint}</span>
      <div className="mt-2">{children}</div>
    </label>
  )
}

const inputCls =
  'w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900 focus:border-inst-500 focus:outline-none'

export default function ScenarioPage() {
  const [stations, setStations] = useState<Station[]>([])
  const [station, setStation] = useState('Anand Vihar')
  const [hours, setHours] = useState(72)
  const [running, setRunning] = useState<'idle' | 'loading' | 'error' | 'done'>('idle')
  const [result, setResult] = useState<ScenarioAnalysisResponse | null>(null)
  const [error, setError] = useState('')

  const [wsMode, setWsMode] = useState<'absolute' | 'relative'>('relative')
  const [wsValue, setWsValue] = useState('1.5')
  const [wdMode, setWdMode] = useState<'absolute' | 'relative'>('relative')
  const [wdValue, setWdValue] = useState('0')
  const [pblMode, setPblMode] = useState<'absolute' | 'relative'>('relative')
  const [pblValue, setPblValue] = useState('1.0')
  const [fireMult, setFireMult] = useState('1.0')
  const [enableChanges, setEnableChanges] = useState<Record<string, boolean>>({
    wind_speed: true,
    wind_direction: false,
    pbl_height: false,
    fire_activity: false,
    inversion: false,
  })
  const [invDetected, setInvDetected] = useState(true)
  const [invStrength, setInvStrength] = useState('0.6')

  useEffect(() => {
    getStations().then((r) => {
      setStations(r.data)
      if (r.data.some((s) => s.name === station)) return
      setStation(r.data[0]?.name ?? 'Anand Vihar')
    }).catch(() => {})
  }, [station])

  const run = useCallback(
    async (ev?: React.FormEvent) => {
      ev?.preventDefault()
      setRunning('loading')
      setError('')
      const changes: ScenarioChangesInput = {
        wind_speed: enableChanges.wind_speed
          ? { mode: wsMode, value: Number(wsValue) || 0 }
          : undefined,
        wind_direction: enableChanges.wind_direction
          ? { mode: wdMode, value: Number(wdValue) || 0 }
          : undefined,
        pbl_height: enableChanges.pbl_height
          ? { mode: pblMode, value: Number(pblValue) || 0 }
          : undefined,
        fire_activity: enableChanges.fire_activity
          ? { mode: 'relative', multiplier: Number(fireMult) || 1 }
          : undefined,
        inversion: enableChanges.inversion
          ? { detected: invDetected, strength: invDetected ? Number(invStrength) || 0 : null }
          : undefined,
      }
      try {
        const res = await postScenarioAnalysis({ station_name: station, hours, changes })
        setResult(res.data)
        setRunning('done')
      } catch (e) {
        const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        setError(typeof detail === 'string' ? detail : 'Scenario analysis failed')
        setRunning('error')
      }
    },
    [enableChanges, wsMode, wsValue, wdMode, wdValue, pblMode, pblValue, fireMult, invDetected, invStrength, station, hours],
  )

  const chartData =
    result?.difference.points.map((p) => ({
      name: hourLabel(p.forecast_horizon),
      Baseline: p.baseline_pm25,
      Scenario: p.scenario_pm25,
      Difference: p.difference_pm25,
    })) ?? []

  const diffBars = chartData.map((d) => ({ name: d.name, Change: +d.Difference.toFixed(1) }))
  const hasResult = running === 'done' && !!result

  return (
    <div className="space-y-6">
      <PageHeader
        title="What-if Scenario Analysis"
        subtitle="Compare a baseline 72 h PM2.5 outlook against a hypothetical change in the atmospheric inputs."
        breadcrumbs={[{ label: 'Tools' }, { label: 'Scenario' }]}
        lastUpdated={result?.generated_at}
      />

      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <p className="flex items-center gap-2 font-semibold">
          <FlaskConical className="h-4 w-4" aria-hidden="true" /> Scenario simulation — not a real forecast
        </p>
        <p className="mt-1 text-xs leading-relaxed">
          Only the inputs you change are perturbed (on an in-memory copy of the current feature row).
          The same trained models are then re-evaluated; the difference is the model&apos;s response to
          your hypothetical — it is not a weather prediction and the database is never modified.
          No causal certainty is claimed.
        </p>
      </div>

      <form onSubmit={run} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Control label="Station" hint="NCR monitoring station whose current inputs are perturbed">
            <select className={inputCls} value={station} onChange={(e) => setStation(e.target.value)}>
              {stations.map((s) => (
                <option key={s.id} value={s.name}>{s.name}</option>
              ))}
            </select>
          </Control>
          <Control label="Forecast horizon" hint="Baseline & scenario horizon (1–72 h)">
            <select
              className={inputCls}
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
            >
              {[6, 12, 24, 48, 72].map((h) => (
                <option key={h} value={h}>{h} hours</option>
              ))}
            </select>
          </Control>
          <Control label="Wind speed" hint="1.5× = 50% stronger winds; 0.5× = half">
            <div className="flex gap-2">
              <select className={inputCls} value={wsMode} onChange={(e) => setWsMode(e.target.value as 'absolute' | 'relative')} disabled={!enableChanges.wind_speed}>
                <option value="relative">× multiplier</option>
                <option value="absolute">m/s absolute</option>
              </select>
              <input
                className={inputCls}
                type="number"
                step="0.1"
                value={wsValue}
                onChange={(e) => setWsValue(e.target.value)}
                disabled={!enableChanges.wind_speed}
                aria-label="Wind speed change value"
              />
            </div>
          </Control>
          <Control label="Regional fire activity" hint="FRP-intensity multiplier on fire-transport terms">
            <input
              className={inputCls}
              type="number"
              step="0.5"
              min="0"
              value={fireMult}
              onChange={(e) => setFireMult(e.target.value)}
              disabled={!enableChanges.fire_activity}
              aria-label="Fire activity multiplier"
            />
          </Control>
          <Control label="PBL height" hint="1.5× = deeper mixing, 0.5× = shallower">
            <div className="flex gap-2">
              <select className={inputCls} value={pblMode} onChange={(e) => setPblMode(e.target.value as 'absolute' | 'relative')} disabled={!enableChanges.pbl_height}>
                <option value="relative">× multiplier</option>
                <option value="absolute">m absolute</option>
              </select>
              <input
                className={inputCls}
                type="number"
                step="0.1"
                value={pblValue}
                onChange={(e) => setPblValue(e.target.value)}
                disabled={!enableChanges.pbl_height}
                aria-label="PBL height change value"
              />
            </div>
          </Control>
          <Control label="Wind direction" hint="Rotation in degrees (relative) or absolute °">
            <div className="flex gap-2">
              <select className={inputCls} value={wdMode} onChange={(e) => setWdMode(e.target.value as 'absolute' | 'relative')} disabled={!enableChanges.wind_direction}>
                <option value="relative">rotate °</option>
                <option value="absolute">° absolute</option>
              </select>
              <input
                className={inputCls}
                type="number"
                step="5"
                value={wdValue}
                onChange={(e) => setWdValue(e.target.value)}
                disabled={!enableChanges.wind_direction}
                aria-label="Wind direction change value"
              />
            </div>
          </Control>
          <Control label="Inversion" hint="Force inversion on/off and set strength 0–1">
            <div className="flex flex-col gap-2">
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={enableChanges.inversion}
                  onChange={(e) => setEnableChanges((v) => ({ ...v, inversion: e.target.checked }))}
                  className="h-4 w-4"
                />
                Enabled
              </label>
              <div className="flex items-center gap-2">
                <select className={inputCls} value={String(invDetected)} onChange={(e) => setInvDetected(e.target.value === 'true')} disabled={!enableChanges.inversion}>
                  <option value="true">Present</option>
                  <option value="false">Absent</option>
                </select>
                <input
                  className={inputCls}
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  value={invStrength}
                  onChange={(e) => setInvStrength(e.target.value)}
                  disabled={!enableChanges.inversion || !invDetected}
                  aria-label="Inversion strength"
                />
              </div>
            </div>
          </Control>
          <Control label="Wind / PBL toggles" hint="Include or exclude a perturbation">
            <div className="flex flex-wrap gap-2 text-xs">
              {(
                [
                  ['wind_speed', 'Wind', wsMode === 'relative' ? `×${wsValue}` : `${wsValue} m/s`],
                  ['wind_direction', 'Dir', wdMode === 'relative' ? `+${wdValue}°` : `${wdValue}°`],
                  ['pbl_height', 'PBLH', pblMode === 'relative' ? `×${pblValue}` : `${pblValue} m`],
                  ['fire_activity', 'Fire', `×${fireMult}`],
                ] as const
              ).map(([key, label, val]) => (
                <label key={key} className="flex items-center gap-1.5 rounded-full border border-slate-200 px-2.5 py-1">
                  <input
                    type="checkbox"
                    checked={enableChanges[key]}
                    onChange={(e) => setEnableChanges((v) => ({ ...v, [key]: e.target.checked }))}
                    className="h-3.5 w-3.5"
                  />
                  {label} {val}
                </label>
              ))}
            </div>
          </Control>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className="btn-primary" disabled={running === 'loading'}>
            {running === 'loading' ? 'Running analysis…' : 'Run baseline vs scenario'}
          </button>
          {hasResult && (
            <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
              <ShieldCheck className="h-4 w-4 text-emerald-600" aria-hidden="true" />
              Read-only: {result.data_integrity.scenario_overwrites_nothing === true ? 'observations untouched' : 'results verified read-only'}
            </span>
          )}
        </div>
      </form>

      {running === 'loading' && <LoadingState label="Running the scenario through the trained models…" />}

      {running === 'error' && (
        <ErrorState message={error || 'Scenario analysis failed'} onRetry={() => setRunning('idle')} />
      )}

      {running === 'idle' && !result && (
        <EmptyState title="No scenario run yet" hint="Set at least one perturbation above and run the comparison." />
      )}

      {hasResult && (
        <>
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs leading-relaxed text-slate-600">
            <p className="font-semibold text-slate-700">Why this is labelled a simulation</p>
            <p>{result.disclaimer}</p>
            <p className="mt-2">
              Model: {result.model} · uncertainty: {result.uncertainty_method ?? 'none shown'} ·
              served horizons: {result.served_horizons.map(hourLabel).join(', ')} ·
              last observed PM2.5: {fmt(result.observed.pm25_last_observed_ugm3)} µg/m³
              {result.observed.timestamp ? ` at ${result.observed.timestamp.replace('T', ' ').slice(0, 16)}` : ''}.
            </p>
            {result.notes.map((n) => (
              <p key={n} className="mt-1 text-amber-800">• {n}</p>
            ))}
          </div>

          <div className="card">
            <h3 className="card-header">Baseline vs scenario PM2.5 (µg/m³)</h3>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
                <XAxis dataKey="name" stroke={CHART.axis} fontSize={11} />
                <YAxis stroke={CHART.axis} fontSize={12} />
                <Tooltip {...tooltipStyle} />
                <Legend />
                <Line type="monotone" dataKey="Baseline" stroke="#64748b" strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="Scenario" stroke={CHART.brand} strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
            <p className="mt-2 text-xs text-slate-500">
              Peak baseline {fmt(result.baseline_forecast.peak_pm25)} vs peak scenario{' '}
              {fmt(result.scene_forecast.peak_pm25)} µg/m³ · mean difference{' '}
              {fmt(result.difference.mean_difference_pm25, 2)} µg/m³
            </p>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card">
              <h3 className="card-header">Per-horizon change (scenario − baseline, µg/m³)</h3>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={diffBars}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
                  <XAxis dataKey="name" stroke={CHART.axis} fontSize={11} />
                  <YAxis stroke={CHART.axis} fontSize={12} />
                  <Tooltip {...tooltipStyle} />
                  <Bar dataKey="Change" radius={[4, 4, 0, 0]}>
                    {diffBars.map((d) => (
                      <Cell key={d.name} fill={d.Change >= 0 ? '#d97706' : '#16a34a'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="mt-2 text-xs text-slate-500">
                Amber = scenario raises PM2.5; green = scenario lowers it. This is the model&apos;s
                response to your input change — a hypothesis, not an outcome that will certainly occur.
              </p>
            </div>

            <div className="card">
              <h3 className="card-header">Input changes applied</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-slate-500">
                      <th className="py-2">Feature</th>
                      <th className="py-2 text-right">Baseline</th>
                      <th className="py-2 text-right">Scenario</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.input_changes.map((c) => (
                      <tr key={c.feature} className="border-b border-slate-100">
                        <td className="py-2 text-slate-900">{c.feature}</td>
                        <td className="py-2 text-right text-slate-600">{fmt(c.baseline_value)} {c.unit ?? ''}</td>
                        <td className="py-2 text-right text-slate-900">{fmt(c.scenario_value)} {c.unit ?? ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-3 flex items-start gap-2 rounded-lg bg-inst-50 p-3 text-xs text-inst-900">
                <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <p>{result.value_kinds.scenario ?? 'Scenario values are model output on the perturbed feature row.'}</p>
              </div>
            </div>
          </div>

          <div className="card">
            <h3 className="card-header">Hourly detail</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-slate-500">
                    <th className="py-2">Horizon</th>
                    <th className="py-2 text-right">Baseline µg/m³</th>
                    <th className="py-2 text-right">Scenario µg/m³</th>
                    <th className="py-2 text-right">Δ µg/m³</th>
                  </tr>
                </thead>
                <tbody>
                  {result.difference.points.map((p) => (
                    <tr key={p.forecast_horizon} className="border-b border-slate-100">
                      <td className="py-2 font-medium text-slate-900">{hourLabel(p.forecast_horizon)}</td>
                      <td className="py-2 text-right text-slate-700">{fmt(p.baseline_pm25)}</td>
                      <td className="py-2 text-right text-slate-900">{fmt(p.scenario_pm25)}</td>
                      <td className={`py-2 text-right font-medium ${p.difference_pm25 >= 0 ? 'text-amber-700' : 'text-emerald-700'}`}>
                        {p.difference_pm25 >= 0 ? '+' : ''}{fmt(p.difference_pm25, 2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}