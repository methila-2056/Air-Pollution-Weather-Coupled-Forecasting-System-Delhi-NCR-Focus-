interface AQICardProps {
  label: string
  value: number | string | null | undefined
  unit?: string
  color?: string
}

function getAQIColor(aqi: number | null): string {
  if (!aqi) return 'text-gray-400'
  if (aqi <= 50) return 'text-green-400'
  if (aqi <= 100) return 'text-yellow-400'
  if (aqi <= 200) return 'text-orange-400'
  if (aqi <= 300) return 'text-red-400'
  if (aqi <= 400) return 'text-purple-400'
  return 'text-red-600'
}

export default function AQICard({ label, value, unit, color }: AQICardProps) {
  const displayColor = color || (typeof value === 'number' && label.includes('AQI') ? getAQIColor(value) : 'text-white')
  return (
    <div className="card">
      <p className="card-header">{label}</p>
      <p className={`stat-value ${displayColor}`}>
        {value ?? '--'}
        {unit && <span className="text-sm font-normal text-gray-400 ml-1">{unit}</span>}
      </p>
    </div>
  )
}
