import type { CouplingData } from '../types'

export default function CouplingPanel({ data }: { data: CouplingData | null }) {
  if (!data) return <div className="card"><p className="text-slate-500">Loading coupling data...</p></div>

  const d = data.diag
  const strengthColor = {
    'strong': 'bg-red-600',
    'moderate': 'bg-orange-500',
    'weak': 'bg-green-600',
  }[d.coupling_strength] || 'bg-slate-400'

  return (
    <div className="card">
      <h3 className="card-header">Weather ↔ Chemistry Coupling</h3>
      <div className="space-y-4">
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span className="text-slate-500">Feedback Strength</span>
            <span className="font-bold uppercase tracking-wide text-slate-900">{d.coupling_strength}</span>
          </div>
          <div className="w-full bg-slate-200 rounded-full h-3">
            <div className={`${strengthColor} h-3 rounded-full transition-all`} style={{ width: `${Math.max(3, Math.min(100, Math.round(d.stability_coupling_index * 100)))}%` }} />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-slate-500 text-xs">Aerosol Optical Depth</p>
            <p className="text-lg font-bold text-slate-900">{d.aod_est.toFixed(3)}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-slate-500 text-xs">Radiation Transmittance</p>
            <p className="text-lg font-bold text-slate-900">{(d.radiation_transmittance * 100).toFixed(0)}%</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-slate-500 text-xs">PBL Suppression</p>
            <p className="text-lg font-bold text-slate-900">{(d.pbl_suppression_factor * 100).toFixed(0)}%</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-slate-500 text-xs">Corrected PBL</p>
            <p className="text-lg font-bold text-slate-900">{d.corrected_pbl_height.toFixed(0)}m</p>
          </div>
        </div>

        <div>
          <span className="text-sm text-slate-500">Coupling Feedback Multiplier: </span>
          <span className="font-bold text-slate-900">{d.feedback_multiplier.toFixed(2)}×</span>
          <span className="text-xs text-slate-500 ml-2">(&gt;1 = trapped)</span>
        </div>

        <div className="border-t border-slate-200 pt-3">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Two-way Feedback Analysis</p>
          <ul className="space-y-1.5">
            {data.narrative.map((line, i) => (
              <li key={i} className="text-sm text-slate-700">• {line}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}