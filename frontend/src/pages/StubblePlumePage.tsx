import { useState, useEffect } from 'react'
import { getPlumeRisk, getFireActivity } from '../api/client'
import StubblePlume from '../components/StubblePlume'
import type { PlumeRisk, FireActivity } from '../types'

export default function StubblePlumePage() {
  const [risk, setRisk] = useState<PlumeRisk | null>(null)
  const [fire, setFire] = useState<FireActivity | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.allSettled([
      getPlumeRisk().then(r => setRisk(r.data)),
      getFireActivity().then(r => setFire(r.data)),
    ]).then(results => {
      if (results.every(r => r.status === 'rejected')) setError('Failed to load fire data')
    })
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Stubble Burning Intelligence</h1>
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">{error}</div>
      )}
      <div className="grid grid-cols-4 gap-4">
        <div className="card"><p className="card-header">Total Fires</p><p className="stat-value">{fire?.total_fires ?? 0}</p></div>
        <div className="card"><p className="card-header">High Confidence</p><p className="stat-value">{fire?.high_confidence_fires ?? 0}</p></div>
        <div className="card"><p className="card-header">Mean FRP</p><p className="stat-value">{fire?.mean_frp?.toFixed(0) ?? 0} MW</p></div>
        <div className="card"><p className="card-header">Region</p><p className="stat-value text-lg">{fire?.region ?? 'N/A'}</p></div>
      </div>
      <div className="grid grid-cols-2 gap-6">
        <StubblePlume data={risk} />
        <div className="card">
          <h3 className="card-header">Methodology</h3>
          <div className="text-sm text-gray-400 space-y-2">
            <p>This module estimates regional fire-plume transport risk based on:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>NASA FIRMS active fire hotspot locations</li>
              <li>Fire Radiative Power (FRP) intensity</li>
              <li>Wind direction and speed alignment</li>
              <li>Distance from Delhi NCR</li>
              <li>Atmospheric dispersion conditions</li>
            </ul>
            <p className="mt-3 text-yellow-400/80">Note: This is an estimated transport risk indicator, not a full atmospheric chemical transport simulation.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
