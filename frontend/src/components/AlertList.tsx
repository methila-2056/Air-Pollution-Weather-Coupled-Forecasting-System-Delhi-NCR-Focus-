import type { Alert } from '../types'
import { AlertTriangle, AlertCircle, Info } from 'lucide-react'

const levelConfig = {
  SEVERE: { icon: AlertTriangle, label: 'Severe', color: 'text-red-700 bg-red-50 border-red-300', chip: 'bg-red-700 text-white' },
  WARNING: { icon: AlertTriangle, label: 'Warning', color: 'text-orange-700 bg-orange-50 border-orange-300', chip: 'bg-orange-600 text-white' },
  ADVISORY: { icon: Info, label: 'Advisory', color: 'text-sky-700 bg-sky-50 border-sky-300', chip: 'bg-sky-600 text-white' },
  WATCH: { icon: AlertCircle, label: 'Watch', color: 'text-amber-700 bg-amber-50 border-amber-300', chip: 'bg-amber-500 text-white' },
  INFO: { icon: Info, label: 'Info', color: 'text-inst-700 bg-inst-50 border-inst-300', chip: 'bg-inst-700 text-white' },
}

export default function AlertList({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length) return <div className="card"><p className="text-slate-500">No active alerts.</p></div>

  return (
    <div className="space-y-3">
      {alerts.map(a => {
        const config = levelConfig[a.alert_level as keyof typeof levelConfig] || levelConfig.INFO
        const Icon = config.icon
        return (
          <div key={a.id} className={`card border ${config.color}`}>
            <div className="flex items-start gap-3">
              <Icon className="mt-0.5 flex-shrink-0" size={20} aria-hidden="true" />
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-slate-900">{a.title}</p>
                  <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${config.chip}`}>
                    {config.label}
                  </span>
                </div>
                <p className="text-sm text-slate-600 mt-1">{a.description}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span>Station: <span className="font-semibold text-slate-700">{a.station}</span></span>
                  {a.forecast_horizon_hours != null && <span>· Horizon: +{a.forecast_horizon_hours}h</span>}
                  {a.created_at && <span>· {a.created_at.replace('T', ' ').slice(0, 16)}</span>}
                </div>
                {a.factors && <p className="text-sm text-slate-700 mt-2">Drivers: {a.factors}</p>}
                {a.recommendation && <p className="text-sm text-slate-700 mt-2">Recommendation: {a.recommendation}</p>}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
