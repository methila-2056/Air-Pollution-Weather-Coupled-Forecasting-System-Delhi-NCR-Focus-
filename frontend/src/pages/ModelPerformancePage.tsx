import { useState, useEffect } from 'react'
import { getModelMetrics } from '../api/client'
import ModelPerformance from '../components/ModelPerformance'
import type { ModelMetric } from '../types'

export default function ModelPerformancePage() {
  const [metrics, setMetrics] = useState<ModelMetric[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getModelMetrics()
      .then(r => setMetrics(r.data))
      .catch(() => setError('Failed to load model metrics'))
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Model Performance</h1>
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">{error}</div>
      )}
      <ModelPerformance metrics={metrics} />
    </div>
  )
}
