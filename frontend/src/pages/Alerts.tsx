import { useState, useEffect } from 'react'
import { getAlerts } from '../api/client'
import AlertList from '../components/AlertList'
import type { Alert } from '../types'

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getAlerts()
      .then(r => setAlerts(r.data))
      .catch(() => setError('Failed to load alerts'))
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Alerts & Warnings</h1>
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">{error}</div>
      )}
      <AlertList alerts={alerts} />
    </div>
  )
}
