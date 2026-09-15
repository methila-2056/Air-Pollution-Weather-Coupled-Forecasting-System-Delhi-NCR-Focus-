import type { Explanation, ForecastExplanation, ShapContribution } from '../types'

function ShapDriverRow({ c, totalPct }: { c: ShapContribution; totalPct: number }) {
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="text-slate-700">{c.description}</span>
        <span className="text-slate-500">
          {c.value !== null && c.value !== undefined ? `${Number(c.value).toFixed(1)}` : 'n/a'} · {c.share_of_abs_contributions_pct.toFixed(1)}%
        </span>
      </div>
      <div className="w-full bg-slate-200 rounded-full h-2">
        <div
          className={`h-2 rounded-full ${c.direction === 'positive' ? 'bg-red-600' : 'bg-inst-500'}`}
          style={{ width: `${(c.share_of_abs_contributions_pct / totalPct) * 100}%` }}
        />
      </div>
    </div>
  )
}

function ShapPanel({ data }: { data: ForecastExplanation }) {
  const delta = data.forecast_pm25 - data.base_value
  const heading =
    delta > 1e-6
      ? `Why is PM2.5 expected to increase to ${data.forecast_pm25.toFixed(1)} µg/m³?`
      : delta < -1e-6
        ? `Why is PM2.5 expected to decrease to ${data.forecast_pm25.toFixed(1)} µg/m³?`
        : `PM2.5 is expected to stay near ${data.forecast_pm25.toFixed(1)} µg/m³.`

  const positives = data.top_positive_drivers.slice(0, 5)
  const negatives = data.top_negative_drivers.slice(0, 5)
  const magnitudes = data.contributions_by_magnitude.slice(0, 5)
  const totalPct = magnitudes.reduce((s, c) => s + c.share_of_abs_contributions_pct, 0) || 1

  const modelsAvailable = data.test_metrics?.mae != null

  return (
    <div className="card">
      <h3 className="card-header">{heading}</h3>
      <p className="text-xs text-slate-500 mb-3">
        {data.summary}
      </p>
      {modelsAvailable && data.test_metrics && (
        <p className="text-xs text-slate-500 mb-3">
          Held-out test MAE {data.test_metrics.mae} · RMSE {data.test_metrics.rmse} · R² {data.test_metrics.r2} (n={data.test_metrics.n})
        </p>
      )}
      <p className="text-xs text-slate-500 mb-3">
        {data.explanation_method} · {data.n_features} features · model base {data.base_value.toFixed(2)}
      </p>
      {positives.length > 0 && (
        <div className="space-y-2 mb-4">
          <p className="text-xs font-semibold text-red-700 uppercase tracking-wide">Top drivers pushing PM2.5 up</p>
          {positives.map((c) => <ShapDriverRow key={c.feature} c={c} totalPct={totalPct} />)}
        </div>
      )}
      {negatives.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-inst-700 uppercase tracking-wide">Top drivers pulling PM2.5 down</p>
          {negatives.map((c) => <ShapDriverRow key={c.feature} c={c} totalPct={totalPct} />)}
        </div>
      )}
    </div>
  )
}

export default function ExplainabilityPanel({ data }: { data: Explanation | ForecastExplanation | null }) {
  if (!data) return <div className="card"><p className="text-slate-500">Loading explanation...</p></div>

  if ('forecast_pm25' in data) {
    return <ShapPanel data={data} />
  }

  const maxImportance = Math.max(...data.top_features.map(f => f.importance), 1)

  return (
    <div className="card">
      <h3 className="card-header">Why is AQI Expected to Change?</h3>
      <div className="space-y-3">
        {data.top_features.map((f, i) => (
          <div key={i}>
            <div className="flex justify-between text-sm mb-1">
              <span className="text-slate-700">{f.description}</span>
              <span className="text-slate-500">{(f.importance / maxImportance * 100).toFixed(0)}%</span>
            </div>
            <div className="w-full bg-slate-200 rounded-full h-2">
              <div
                className={`h-2 rounded-full ${f.direction === 'positive' ? 'bg-red-600' : 'bg-inst-500'}`}
                style={{ width: `${(f.importance / maxImportance) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}