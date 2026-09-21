import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, LineChart, Line } from 'recharts'
import type { ModelPerformanceResponse } from '../types'
import { CHART } from '../lib/theme'

const MODEL_LABELS: Record<string, string> = {
  persistence: 'Persistence',
  random_forest: 'Random Forest',
  xgboost: 'XGBoost',
  gru: 'GRU',
}

const MODEL_COLORS: Record<string, string> = {
  persistence: '#64748b',
  random_forest: '#16a34a',
  xgboost: CHART.brand,
  gru: '#7c3aed',
}

const tooltipStyle = {
  contentStyle: { backgroundColor: CHART.tooltipBg, border: `1px solid ${CHART.tooltipBorder}`, borderRadius: 8 },
  labelStyle: { color: CHART.tooltipLabel },
}

function fmt(v: number | null | undefined, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return v.toFixed(digits)
}

function dateFmt(s: string | null | undefined) {
  if (!s) return '--'
  const cleaned = s.endsWith('Z') || s.includes('+00:00') ? s : `${s}Z`
  const d = new Date(cleaned)
  if (Number.isNaN(d.getTime())) return s.replace('T', ' ').slice(0, 16)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function pct(v: number | null | undefined) {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return `${(v * 100).toFixed(1)}%`
}

export default function ModelPerformance({ data }: { data: ModelPerformanceResponse }) {
  if (!data.results?.length) {
    return <div className="card"><p className="text-slate-500">No measured metrics available yet.</p></div>
  }

  const models = data.evaluated_models ?? Object.keys(data.results[0].metrics)
  const target = data.target ?? 'pm25'

  // MAE grouped by horizon (xgb + rf + persistence)
  const chartData = data.results.map(r => {
    const row: Record<string, number | string> = { name: `+${r.horizon_hours}h` }
    for (const m of models) {
      if (r.metrics[m]?.mae != null) row[MODEL_LABELS[m] ?? m] = +r.metrics[m].mae.toFixed(2)
    }
    return row
  })

  // R² by horizon
  const r2Data = data.results.map(r => {
    const row: Record<string, number | string> = { name: `+${r.horizon_hours}h` }
    for (const m of models) {
      if (r.metrics[m]?.r2 != null) row[MODEL_LABELS[m] ?? m] = +r.metrics[m].r2.toFixed(3)
    }
    return row
  })

  const splitEntries = Object.entries(data.split_ranges ?? {})

  return (
    <div className="space-y-6">
      {/* Context / summary */}
<div className="card">
        <h3 className="card-header">Measured Test-Set Performance</h3>
        <p className="text-sm text-slate-600 mb-4">
          Target: <span className="font-semibold text-slate-900">{data.target?.toUpperCase()}</span> |
          Models: {data.evaluated_models?.join(', ')} |
          Features: <span className="font-semibold text-slate-900">{data.feature_count}</span> |
          Horizons: {data.horizons?.map(h => `+${h}h`).join(', ')}
          <br />
          Split: {data.split_type} — all metrics computed on the held-out test period only,
          measured at {dateFmt(data.generated_at)}.
        </p>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 border-b border-slate-200">
                <th className="text-left py-2">Split</th>
                <th className="text-left py-2">Start</th>
                <th className="text-left py-2">End</th>
                <th className="text-right py-2">Rows</th>
              </tr>
            </thead>
            <tbody>
              {splitEntries.map(([name, s]) => (
                <tr key={name} className="border-b border-slate-100">
                  <td className="py-2 text-slate-900 capitalize">{name}</td>
                  <td className="py-2 text-slate-700">{dateFmt(s.start)}</td>
                  <td className="py-2 text-slate-700">{dateFmt(s.end)}</td>
                  <td className="text-right py-2 text-slate-700">{s.n_rows?.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* MAE chart */}
      <div className="card">
        <h3 className="card-header">Mean Absolute Error by Horizon (lower is better)</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
            <XAxis dataKey="name" stroke={CHART.axis} fontSize={11} />
            <YAxis stroke={CHART.axis} fontSize={12} />
            <Tooltip {...tooltipStyle} />
            <Legend />
            {models.map(m => (
              <Bar key={m} dataKey={MODEL_LABELS[m] ?? m} fill={MODEL_COLORS[m] ?? CHART.brand} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* R² chart */}
      <div className="card">
        <h3 className="card-header">R-squared by Horizon (higher is better)</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={r2Data}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
            <XAxis dataKey="name" stroke={CHART.axis} fontSize={11} />
            <YAxis stroke={CHART.axis} fontSize={12} domain={[0, 1]} />
            <Tooltip {...tooltipStyle} />
            <Legend />
            {models.map(m => (
              <Line key={m} type="monotone" dataKey={MODEL_LABELS[m] ?? m} stroke={MODEL_COLORS[m] ?? CHART.brand} strokeWidth={2} dot={{ r: 3 }} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Full comparison table */}
      <div className="card">
        <h3 className="card-header">Detailed Metrics (MAE / RMSE / R-squared)</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 border-b border-slate-200">
                <th className="text-left py-2">Horizon</th>
                {models.map(m => (
                  <th key={m} className="text-left py-2 px-2">{MODEL_LABELS[m] ?? m}</th>
                ))}
                <th className="text-right py-2">N (test)</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map(r => (
                <tr key={r.horizon_hours} className="border-b border-slate-100">
                  <td className="py-2 font-medium text-slate-900">+{r.horizon_hours}h</td>
                  {models.map(m => {
                    const mm = r.metrics[m]
                    return (
                      <td key={m} className="py-2 px-2 text-xs text-slate-700">
                        MAE {fmt(mm?.mae)} · RMSE {fmt(mm?.rmse)} · R² {fmt(mm?.r2, 3)}
                      </td>
                    )
                  })}
                  <td className="text-right py-2 text-slate-700">{r.n_test?.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-slate-500 mt-3">
          Persistence = last observed {target.toUpperCase()} ({target}_lag1). Test period shown
          per horizon; all models are scored on the exact same rows.
        </p>
      </div>

      {/* Conformal interval coverage (honest held-out verification) */}
      {data.results.some(r => r.coverage?.models) && (
        <div className="card">
          <h3 className="card-header">Conformal Interval Coverage (held-out test)</h3>
          <p className="text-sm text-slate-600 mb-4">
            Split-conformal half-widths are calibrated on the validation (calibration) set only
            (target {pct(data.results[0]?.coverage?.target ?? 0.85)}); the table reports the measured
            fraction of held-out test rows inside each interval. Coverage below the target is
            reported as-is — no claim beyond the measured value.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 border-b border-slate-200">
                  <th className="text-left py-2">Horizon</th>
                  {models.map(m => (
                    <th key={m} className="text-left py-2 px-2">{MODEL_LABELS[m] ?? m}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.results.map(r => (
                  <tr key={r.horizon_hours} className="border-b border-slate-100">
                    <td className="py-2 font-medium text-slate-900">+{r.horizon_hours}h</td>
                    {models.map(m => {
                      const c = r.coverage?.models?.[m]
                      if (!c) return <td key={m} className="py-2 px-2 text-xs text-slate-400">--</td>
                      const measured = c.test_coverage ?? null
                      const targetCov = r.coverage?.target ?? c.coverage_target ?? 0.85
                      const ok = measured !== null && measured >= targetCov - 0.005
                      return (
                        <td key={m} className="py-2 px-2 text-xs">
                          width {fmt(c.quantile)} · measured{' '}
                          <span className={ok ? 'text-emerald-700 font-medium' : 'text-amber-700 font-medium'}>
                            {pct(measured)}
                          </span>
                          <span className="text-slate-400"> / {pct(targetCov)}</span>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-slate-500 mt-3">
            Width = calibrated half-interval (±) in {target.toUpperCase()} units. N(cal) per
            horizon equals the validation split size shown above.
          </p>
        </div>
      )}
    </div>
  )
}
