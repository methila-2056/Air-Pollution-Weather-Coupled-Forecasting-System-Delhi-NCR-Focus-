import type { InversionData } from '../types'

function layerLabel(data: InversionData): string {
  if (data.inversion_base_pressure && data.inversion_top_pressure) {
    return `${data.inversion_base_pressure.toFixed(0)}–${data.inversion_top_pressure.toFixed(0)} hPa`
  }
  return '--'
}

export default function InversionPanel({ data }: { data: InversionData | null }) {
  if (!data) return <div className="card"><p className="text-gray-400">Loading inversion data...</p></div>

  const strengthColor = {
    'Strong': 'bg-red-500',
    'Moderate': 'bg-orange-500',
    'Weak': 'bg-yellow-500',
    'None': 'bg-green-500',
  }[data.inversion_strength] || 'bg-gray-500'

  const riskColor = {
    'HIGH': 'text-red-400',
    'MEDIUM': 'text-orange-400',
    'LOW': 'text-yellow-400',
    'MINIMAL': 'text-green-400',
  }[data.trapping_risk] || 'text-gray-400'

  const dispColor = {
    'TRAPPED': 'text-red-400',
    'LIMITED': 'text-orange-400',
    'MODERATE': 'text-yellow-400',
    'GOOD': 'text-green-400',
  }[data.dispersion_condition ?? ''] || 'text-gray-400'

  const pct = data.inversion_strength_score != null ? Math.round(data.inversion_strength_score * 100) : null
  const width = data.inversion_strength === 'Strong'
    ? '100%'
    : data.inversion_strength === 'Moderate'
    ? '65%'
    : data.inversion_strength === 'Weak'
    ? '35%'
    : '10%'

  return (
    <div className="card">
      <h3 className="card-header">Inversion Status</h3>
      <div className="space-y-4">
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span className="text-gray-400">Strength</span>
            <span className="font-medium">{data.inversion_strength}{pct !== null ? ` (${pct}%)` : ''}</span>
          </div>
          <div className="w-full bg-navy-700 rounded-full h-3">
            <div className={`${strengthColor} h-3 rounded-full transition-all`} style={{ width }} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-gray-400">PBL Height: </span>
            <span className="font-medium">{data.pbl_height ? `${data.pbl_height}m` : '--'}</span>
          </div>
          <div>
            <span className="text-gray-400">Inversion layer: </span>
            <span className="font-medium">{data.inversion_source === 'lapse_rate' ? layerLabel(data) : '--'}</span>
          </div>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Basis</span>
          <span className="font-medium">
            {data.inversion_source === 'lapse_rate'
              ? `Vertical lapse rate (${data.strongest_layer_gradient?.toFixed(2) ?? '--'} K/100hPa)`
              : 'PBL proxy (no vertical profile)'}
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Pollution Trapping</span>
          <span className={`font-bold ${riskColor}`}>{data.trapping_risk}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Dispersion Condition</span>
          <span className={`font-bold ${dispColor}`}>{data.dispersion_condition ?? '--'}</span>
        </div>
      </div>
    </div>
  )
}