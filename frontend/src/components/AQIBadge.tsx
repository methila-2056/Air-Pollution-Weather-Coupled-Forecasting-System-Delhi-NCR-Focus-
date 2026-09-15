import { aqiStyle } from '../lib/aqi'

interface AQIBadgeProps {
  category: string | null
  aqi?: number | null
}

export default function AQIBadge({ category, aqi }: AQIBadgeProps) {
  const style =
    typeof aqi === 'number' && !Number.isNaN(aqi)
      ? aqiStyle(aqi).chip
      : aqiStyle(null).chip
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${style}`}>
      {aqi !== undefined && aqi !== null && <span className="tabular-nums">{aqi}</span>}
      {category ?? 'No data'}
    </span>
  )
}