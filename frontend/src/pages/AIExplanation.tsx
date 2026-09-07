import { useState, useEffect } from 'react'
import { getStations, getExplanation } from '../api/client'
import ExplainabilityPanel from '../components/ExplainabilityPanel'
import type { Station, Explanation } from '../types'

export default function AIExplanation() {
  const [stations, setStations] = useState<Station[]>([])
  const [selected, setSelected] = useState('Anand Vihar')
  const [explanation, setExplanation] = useState<Explanation | null>(null)

  useEffect(() => { getStations().then(r => setStations(r.data)).catch(() => {}) }, [])
  useEffect(() => { getExplanation(selected).then(r => setExplanation(r.data)).catch(() => {}) }, [selected])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">AI Explanation</h1>
      <select value={selected} onChange={e => setSelected(e.target.value)} className="bg-navy-800 border border-navy-700 rounded-lg px-4 py-2 text-sm">
        {stations.map(s => <option key={s.id} value={s.name}>{s.name}</option>)}
      </select>
      <ExplainabilityPanel data={explanation} />
      <div className="card">
        <h3 className="card-header">Natural Language Explanation</h3>
        <div className="space-y-2">
          {explanation?.natural_language.map((text, i) => (
            <p key={i} className="text-gray-300 text-sm">• {text}</p>
          ))}
        </div>
      </div>
    </div>
  )
}
