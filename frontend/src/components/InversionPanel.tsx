import type { InversionData } from '../types'

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

  return (
    <div className="card">
      <h3 className="card-header">Inversion Status</h3>
      <div className="space-y-4">
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span className="text-gray-400">Strength</span>
            <span className="font-medium">{data.inversion_strength}</span>
          </div>
          <div className="w-full bg-navy-700 rounded-full h-3">
            <div className={`${strengthColor} h-3 rounded-full transition-all`} style={{ width: data.inversion_strength === 'Strong' ? '100%' : data.inversion_strength === 'Moderate' ? '65%' : data.inversion_strength === 'Weak' ? '35%' : '10%' }} />
          </div>
        </div>
        <div>
          <span className="text-sm text-gray-400">PBL Height: </span>
          <span className="font-medium">{data.pbl_height ? `${data.pbl_height}m` : '--'}</span>
        </div>
        <div>
          <span className="text-sm text-gray-400">Pollution Trapping: </span>
          <span className={`font-bold ${riskColor}`}>{data.trapping_risk}</span>
        </div>
      </div>
    </div>
  )
}
