import type { Alert } from '../types'
import { AlertTriangle, AlertCircle, Info } from 'lucide-react'

const levelConfig = {
  SEVERE: { icon: AlertTriangle, color: 'text-red-400 bg-red-500/10 border-red-500/30' },
  WARNING: { icon: AlertTriangle, color: 'text-orange-400 bg-orange-500/10 border-orange-500/30' },
  WATCH: { icon: AlertCircle, color: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30' },
  INFO: { icon: Info, color: 'text-blue-400 bg-blue-500/10 border-blue-500/30' },
}

export default function AlertList({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length) return <div className="card"><p className="text-gray-400">No active alerts.</p></div>

  return (
    <div className="space-y-3">
      {alerts.map(a => {
        const config = levelConfig[a.alert_level as keyof typeof levelConfig] || levelConfig.INFO
        const Icon = config.icon
        return (
          <div key={a.id} className={`card border ${config.color}`}>
            <div className="flex items-start gap-3">
              <Icon className="mt-0.5 flex-shrink-0" size={20} />
              <div>
                <p className="font-semibold">{a.title}</p>
                <p className="text-sm text-gray-400 mt-1">{a.description}</p>
                {a.recommendation && <p className="text-sm text-gray-500 mt-2">Recommendation: {a.recommendation}</p>}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
