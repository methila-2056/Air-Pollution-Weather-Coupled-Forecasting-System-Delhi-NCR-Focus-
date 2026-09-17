import { useEffect, useState } from 'react'
import { getGrapStages } from '../api/client'
import { readableOnHex } from '../lib/aqi'
import LoadingState from './LoadingState'
import type { GrapStage } from '../types'

export default function GrapStagesTable() {
  const [stages, setStages] = useState<GrapStage[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getGrapStages()
      .then((r) => setStages(r.data.stages))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingState label="Loading GRAP stages" rows={1} />
  if (!stages.length) return null

  return (
    <div className="mt-6">
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
        CAQM GRAP stage matrix (Oct-2024 revision)
      </h4>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full border-collapse bg-white text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <th className="py-2 pl-3 pr-3 font-medium">Stage</th>
              <th className="py-2 pr-3 font-medium">AQI range</th>
              <th className="py-2 pr-3 font-medium">Summary</th>
              <th className="py-2 pr-3 font-medium">Key measures</th>
            </tr>
          </thead>
          <tbody>
            {stages.map((s) => (
              <tr key={s.stage} className="border-b border-slate-100 align-top last:border-b-0">
                <td className="py-2 pl-3 pr-3">
                  <span
                    className="inline-flex items-center rounded-full px-3 py-0.5 text-xs font-bold"
                    style={{ backgroundColor: s.color, color: readableOnHex(s.color) }}
                  >
                    {s.title}
                  </span>
                </td>
                <td className="py-2 pr-3 text-slate-700">
                  {s.aqi_range_low != null && s.aqi_range_high != null
                    ? `${s.aqi_range_low} – ${s.aqi_range_high}`
                    : '—'}
                  {s.categories.length > 0 && (
                    <span className="ml-1 text-xs text-slate-400">({s.categories.join(', ')})</span>
                  )}
                </td>
                <td className="py-2 pr-3 text-slate-600">{s.summary}</td>
                <td className="py-2 pr-3 text-slate-600">
                  <ul className="space-y-0.5">
                    {s.measures.slice(0, 4).map((m, i) => (
                      <li key={i} className="flex gap-1">
                        <span className="text-inst-700" aria-hidden="true">·</span>
                        <span>{m}</span>
                      </li>
                    ))}
                  </ul>
                  {s.measures.length > 4 && (
                    <p className="mt-0.5 text-[10px] text-slate-400">+ {s.measures.length - 4} more</p>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}