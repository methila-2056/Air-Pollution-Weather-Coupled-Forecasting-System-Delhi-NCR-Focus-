import { aqiStyle } from '../lib/aqi'

interface AQIBadgeProps {
  category: string | null
  aqi?: number | null
  /**
   * Whether the badge also renders the numeric value. On by default.
   *
   * Set this to false wherever a larger readout already shows the same number
   * directly beside the badge. Printing the value twice -- a large `425`
   * followed by a chip reading `425.4` -- looks like a rendering glitch rather
   * than a deliberate readout. The chip colour is derived from `aqi`
   * regardless, so a hidden value costs no severity signal.
   */
  showValue?: boolean
}

export default function AQIBadge({ category, aqi, showValue = true }: AQIBadgeProps) {
  const style =
    typeof aqi === 'number' && !Number.isNaN(aqi)
      ? aqiStyle(aqi).chip
      : aqiStyle(null).chip
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${style}`}>
      {showValue && aqi !== undefined && aqi !== null && <span className="tabular-nums">{aqi}</span>}
      {category ?? 'No data'}
    </span>
  )
}