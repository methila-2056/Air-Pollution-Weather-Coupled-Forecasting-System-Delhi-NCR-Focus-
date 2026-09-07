import type { Explanation } from '../types'

export default function ExplainabilityPanel({ data }: { data: Explanation | null }) {
  if (!data) return <div className="card"><p className="text-gray-400">Loading explanation...</p></div>

  const maxImportance = Math.max(...data.top_features.map(f => f.importance), 1)

  return (
    <div className="card">
      <h3 className="card-header">Why is AQI Expected to Change?</h3>
      <div className="space-y-3">
        {data.top_features.map((f, i) => (
          <div key={i}>
            <div className="flex justify-between text-sm mb-1">
              <span>{f.description}</span>
              <span className="text-gray-400">{(f.importance / maxImportance * 100).toFixed(0)}%</span>
            </div>
            <div className="w-full bg-navy-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full ${f.direction === 'positive' ? 'bg-red-500' : 'bg-blue-500'}`}
                style={{ width: `${(f.importance / maxImportance) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
