import { useState, useEffect } from 'react'
import { getModelMetrics } from '../api/client'
import ModelPerformance from '../components/ModelPerformance'
import type { ModelMetric } from '../types'

export default function ModelPerformancePage() {
  const [metrics, setMetrics] = useState<ModelMetric[]>([])
  useEffect(() => { getModelMetrics().then(r => setMetrics(r.data)).catch(() => {}) }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Model Performance</h1>
      <ModelPerformance metrics={metrics} />
    </div>
  )
}
