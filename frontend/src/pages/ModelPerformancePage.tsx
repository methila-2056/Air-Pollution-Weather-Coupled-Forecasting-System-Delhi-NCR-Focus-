import { useEffect, useState } from 'react'
import { ChartNoAxesCombined } from 'lucide-react'
import { getModelPerformance } from '../api/client'
import PageHeader from '../components/PageHeader'
import LoadingState from '../components/LoadingState'
import ErrorState from '../components/ErrorState'
import ModelPerformance from '../components/ModelPerformance'
import type { ModelPerformanceResponse } from '../types'

const POLLUTANTS = [
  { id: 'pm25', label: 'PM2.5' },
  { id: 'pm10', label: 'PM10' },
  { id: 'o3', label: 'O\u2083' },
  { id: 'no2', label: 'NO\u2082' },
  { id: 'so2', label: 'SO\u2082' },
  { id: 'co', label: 'CO' },
]

export default function ModelPerformancePage() {
  const [target, setTarget] = useState('pm25')
  const [data, setData] = useState<ModelPerformanceResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = (t: string) => {
    setLoading(true)
    setError(null)
    getModelPerformance(t)
      .then((r) => setData(r.data))
      .catch(() =>
        setError(
          `Failed to load measured model metrics for ${t.toUpperCase()}. Run ` +
            '`python -m ml.training.evaluate_pm25 --target ' +
            `${t}` +
            '` first.'
        )
      )
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(target) }, [target])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Model Performance"
        subtitle="Held-out test-set verification of every forecasting model"
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Model Performance' }]}
        lastUpdated={data?.generated_at}
      />

      <div className="card">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-slate-600">Pollutant:</span>
          <div className="flex flex-wrap gap-2">
            {POLLUTANTS.map(p => (
              <button
                key={p.id}
                onClick={() => setTarget(p.id)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  target === p.id
                    ? 'bg-inst-700 text-white'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <LoadingState label={`Loading ${target.toUpperCase()} measured metrics`} rows={2} />
      ) : error ? (
        <ErrorState title="Metrics unavailable" message={error} onRetry={() => load(target)} />
      ) : data ? (
        <>
          <div className="flex items-center gap-2">
            <ChartNoAxesCombined className="h-4 w-4 text-inst-700" aria-hidden="true" />
            <p className="text-xs text-slate-500">
              Deeper per-horizon MAE / RMSE / R² tables and split ranges are available in the
              model evaluation notebook and the <code>ml/training/evaluate_pm25</code> CLI.
              Every model is trained and scored with the identical chronological methodology;
              XGBoost is the deployed runtime model.
            </p>
          </div>
          <ModelPerformance data={data} />
        </>
      ) : null}
    </div>
  )
}