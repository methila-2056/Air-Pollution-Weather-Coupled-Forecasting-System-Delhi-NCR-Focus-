import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, LineChart, Line } from 'recharts'
import type { ModelPerformanceResponse } from '../types'

const MODEL_LABELS: Record<string, string> = {
  persistence: 'Persistence',
  random_forest: 'Random Forest',
  xgboost: 'XGBoost',
}

const MODEL_COLORS: Record<string, string> = {
  persistence: '#6b7280',
  random_forest: '#22c55e',
  xgboost: '#3b82f6',
}

const tooltipStyle = {
  contentStyle: { backgroundColor: '#111640', border: '1px solid #252b68', borderRadius: 8 },
}

function fmt(v: number | null | undefined, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return v.toFixed(digits)
}

function dateFmt(s: string | null | undefined) {
  if (!s) return '--'
  return s.replace('T', ' ').slice(0, 16)
}

export default function ModelPerformance({ data }: { data: ModelPerformanceResponse }) {
  if (!data.results?.length) {
    return <div className="card"><p className="text-gray-400">No measured metrics available yet.</p></div>
  }

  const models = data.evaluated_models ?? Object.keys(data.results[0].metrics)

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
        <p className="text-sm text-gray-400 mb-4">
          Target: <span className="text-gray-200">{data.target?.toUpperCase()}</span> |
          Models: {data.evaluated_models?.join(', ')} |
          Features: <span className="text-gray-200">{data.feature_count}</span> |
          Horizons: {data.horizons?.map(h => `+${h}h`).join(', ')}
          <br />
          Split: {data.split_type} — all metrics computed on the held-out test period only,
          measured at {dateFmt(data.generated_at)}.
        </p>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-navy-700">
                <th className="text-left py-2">Split</th>
                <th className="text-left py-2">Start</th>
                <th className="text-left py-2">End</th>
                <th className="text-right py-2">Rows</th>
              </tr>
            </thead>
            <tbody>
              {splitEntries.map(([name, s]) => (
                <tr key={name} className="border-b border-navy-700/50">
                  <td className="py-2 capitalize">{name}</td>
                  <td className="py-2">{dateFmt(s.start)}</td>
                  <td className="py-2">{dateFmt(s.end)}</td>
                  <td className="text-right py-2">{s.n_rows?.toLocaleString()}</td>
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
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1f52" />
            <XAxis dataKey="name" stroke="#6b7280" fontSize={11} />
            <YAxis stroke="#6b7280" fontSize={12} />
            <Tooltip {...tooltipStyle} />
            <Legend />
            {models.map(m => (
              <Bar key={m} dataKey={MODEL_LABELS[m] ?? m} fill={MODEL_COLORS[m] ?? '#3b82f6'} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* R² chart */}
      <div className="card">
        <h3 className="card-header">R-squared by Horizon (higher is better)</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={r2Data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1f52" />
            <XAxis dataKey="name" stroke="#6b7280" fontSize={11} />
            <YAxis stroke="#6b7280" fontSize={12} domain={[0, 1]} />
            <Tooltip {...tooltipStyle} />
            <Legend />
            {models.map(m => (
              <Line key={m} type="monotone" dataKey={MODEL_LABELS[m] ?? m} stroke={MODEL_COLORS[m] ?? '#3b82f6'} strokeWidth={2} dot={{ r: 3 }} />
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
              <tr className="text-gray-400 border-b border-navy-700">
                <th className="text-left py-2">Horizon</th>
                {models.map(m => (
                  <th key={m} className="text-left py-2 px-2">{MODEL_LABELS[m] ?? m}</th>
                ))}
                <th className="text-right py-2">N (test)</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map(r => (
                <tr key={r.horizon_hours} className="border-b border-navy-700/50">
                  <td className="py-2 font-medium">+{r.horizon_hours}h</td>
                  {models.map(m => {
                    const mm = r.metrics[m]
                    return (
                      <td key={m} className="py-2 px-2 text-xs">
                        MAE {fmt(mm?.mae)} · RMSE {fmt(mm?.rmse)} · R² {fmt(mm?.r2, 3)}
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
          Persistence = last observed PM2.5 (pm25_lag1). Test period shown per horizon;
          all three models are scored on the exact same rows.
        </p>
      </div>
    </div>
  )
}
