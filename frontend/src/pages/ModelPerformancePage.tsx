import { useEffect, useState } from 'react'
import { ChartNoAxesCombined } from 'lucide-react'
import { getModelPerformance } from '../api/client'
import PageHeader from '../components/PageHeader'
import LoadingState from '../components/LoadingState'
import ErrorState from '../components/ErrorState'
import ModelPerformance from '../components/ModelPerformance'
import type { ModelPerformanceResponse } from '../types'

export default function ModelPerformancePage() {
  const [data, setData] = useState<ModelPerformanceResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    setError(null)
    getModelPerformance()
      .then((r) => setData(r.data))
      .catch(() => setError('Failed to load measured model metrics. Run `python -m ml.training.evaluate_pm25` first.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  return (
    <div className="space-y-6">
      <PageHeader
        title="Model Performance"
        subtitle="Held-out test-set verification of every forecasting model"
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Model Performance' }]}
        lastUpdated={data?.generated_at}
      />

      {loading ? (
        <LoadingState label="Loading measured metrics" rows={2} />
      ) : error ? (
        <ErrorState title="Metrics unavailable" message={error} onRetry={load} />
      ) : data ? (
        <>
          <div className="flex items-center gap-2">
            <ChartNoAxesCombined className="h-4 w-4 text-inst-700" aria-hidden="true" />
            <p className="text-xs text-slate-500">
              Deeper per-horizon MAE / RMSE / R² tables and split ranges are available in the model
              evaluation notebook and the <code>ml/training/evaluate_pm25</code> CLI.
            </p>
          </div>
          <ModelPerformance data={data} />
        </>
      ) : null}
    </div>
  )
}