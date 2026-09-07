import { useState, useEffect } from 'react'
import { getAlerts } from '../api/client'
import AlertList from '../components/AlertList'
import type { Alert } from '../types'

export default function Alerts() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  useEffect(() => { getAlerts().then(r => setAlerts(r.data)).catch(() => {}) }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Alerts & Warnings</h1>
      <AlertList alerts={alerts} />
    </div>
  )
}
