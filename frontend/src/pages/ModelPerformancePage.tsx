import { useState, useEffect } from 'react'
import { getModelPerformance } from '../api/client'
import ModelPerformance from '../components/ModelPerformance'
import type { ModelPerformanceResponse } from '../types'

export default function ModelPerformancePage() {
  const [data, setData] = useState<ModelPerformanceResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getModelPerformance()
      .then(r => setData(r.data))
      .catch(() => setError('Failed to load measured model metrics. Run `python -m ml.training.evaluate_pm25` first.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Model Performance</h1>
      {loading && <div className="card text-gray-400">Loading measured metrics...</div>}
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">{error}</div>
      )}
      {data && <ModelPerformance data={data} />}
    </div>
  )
}
