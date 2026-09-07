const CATEGORY_STYLES: Record<string, string> = {
  Good: 'bg-green-500/20 text-green-300 border-green-500/40',
  Satisfactory: 'bg-lime-500/20 text-lime-300 border-lime-500/40',
  Moderate: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
  Poor: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  'Very Poor': 'bg-red-500/20 text-red-300 border-red-500/40',
  Severe: 'bg-red-900/40 text-red-200 border-red-800',
}

interface AQIBadgeProps {
  category: string | null
  aqi?: number | null
}

export default function AQIBadge({ category, aqi }: AQIBadgeProps) {
  const style = CATEGORY_STYLES[category ?? ''] ?? 'bg-zinc-700/40 text-zinc-300 border-zinc-600'
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {aqi !== undefined && aqi !== null && <span className="tabular-nums">{aqi}</span>}
      {category ?? 'Unknown'}
    </span>
  )
}