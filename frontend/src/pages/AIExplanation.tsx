import { useState, useEffect } from 'react'
import { getStations, getExplanation } from '../api/client'
import ExplainabilityPanel from '../components/ExplainabilityPanel'
import PageHeader from '../components/PageHeader'
import type { Station, Explanation } from '../types'

export default function AIExplanation() {
  const [stations, setStations] = useState<Station[]>([])
  const [selected, setSelected] = useState('Anand Vihar')
  const [explanation, setExplanation] = useState<Explanation | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { getStations().then(r => setStations(r.data)).catch(() => {}) }, [])
  useEffect(() => {
    setError(null)
    getExplanation(selected)
      .then(r => setExplanation(r.data))
      .catch(() => setError('Failed to load explanation'))
  }, [selected])

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Explanation"
        subtitle="Why the model predicts what it predicts — station-level natural language and feature attribution"
        breadcrumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'AI Explanation' }]}
        actions={
          <select value={selected} onChange={e => setSelected(e.target.value)} className="select" aria-label="Select station">
            {stations.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
          </select>
        }
      />
      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
      <ExplainabilityPanel data={explanation} />
      <div className="card">
        <h3 className="card-header">Natural Language Explanation</h3>
        <div className="space-y-2">
          {explanation?.natural_language.map((text, i) => (
            <p key={i} className="text-sm text-slate-700">• {text}</p>
          ))}
          {!explanation && !error && <p className="text-sm text-slate-500">Select a station to view explanation.</p>}
        </div>
      </div>
    </div>
  )
}