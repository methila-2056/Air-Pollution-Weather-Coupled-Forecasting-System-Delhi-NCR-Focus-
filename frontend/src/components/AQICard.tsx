import { aqiStyle } from '../lib/aqi'

interface AQICardProps {
  label: string
  value: number | string | null | undefined
  unit?: string
  color?: string
}

export default function AQICard({ label, value, unit, color }: AQICardProps) {
  const isNumeric = typeof value === 'number' && !Number.isNaN(value)
  const displayColor =
    color ??
    (isNumeric && label.toUpperCase().includes('AQI')
      ? aqiStyle(value as number).text
      : 'text-slate-900')
  return (
    <div className="card">
      <p className="card-header">{label}</p>
      <p className={`stat-value ${displayColor}`}>
        {value ?? '--'}
        {unit && <span className="ml-1 text-sm font-normal text-slate-400">{unit}</span>}
      </p>
    </div>
  )
}