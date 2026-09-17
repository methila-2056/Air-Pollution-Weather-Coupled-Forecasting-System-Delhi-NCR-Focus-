import { ArrowRight, Flame, Radar, ShieldAlert, Wind } from 'lucide-react'
import type { FireActivity, TransportRiskResponse } from '../types'
import { fmt } from '../lib/aqi'
import EmptyState from './EmptyState'

interface Props {
  transport: TransportRiskResponse | null
  fire: FireActivity | null
}

interface ChainStep {
  label: string
  value: string
  sub?: string
  icon: typeof Flame
  tone: string
}

export default function TransportChain({ transport, fire }: Props) {
  if (!transport && !fire) {
    return (
      <section className="card">
        <div className="card-header mb-4">Regional transport chain</div>
        <EmptyState title="No transport data" hint="Fire-detection and transport-risk endpoints are currently unavailable." />
      </section>
    )
  }

  const dw = (transport?.dominant_wind_direction ?? {}) as Record<string, unknown>

  const steps: ChainStep[] = [
    {
      label: 'Regional fires',
      value: String(fire?.total_fires ?? transport?.fire_count ?? '--'),
      sub: `mean FRP ${fmt(fire?.mean_frp ?? null, 1)} MW`,
      icon: Flame,
      tone: 'bg-orange-50 text-orange-600',
    },
    {
      label: 'Upwind of NCR',
      value: String(transport?.upwind_fire_count ?? '--'),
      sub: 'within transport estimate',
      icon: Radar,
      tone: 'bg-amber-50 text-amber-600',
    },
    {
      label: 'Wind from',
      value: String(dw.compass_from ?? '--'),
      sub: `${fmt(dw.wind_speed_mps as number | null | undefined ?? null, 1)} m/s`,
      icon: Wind,
      tone: 'bg-sky-50 text-sky-600',
    },
  ]

  const riskTone =
    transport?.risk_level === 'HIGH'
      ? 'text-red-700'
      : transport?.risk_level === 'MODERATE'
        ? 'text-amber-700'
        : 'text-green-700'
  const riskBg =
    transport?.risk_level === 'HIGH'
      ? 'bg-red-50 border-red-200'
      : transport?.risk_level === 'MODERATE'
        ? 'bg-amber-50 border-amber-200'
        : 'bg-green-50 border-green-200'

  return (
    <section className="card">
      <div className="mb-4 flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 text-inst-700" aria-hidden="true" />
        <h2 className="text-base font-bold text-slate-900">Regional transport chain</h2>
        <span className="ml-auto rounded-full bg-inst-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-inst-800">
          Live diagnostics
        </span>
      </div>

      <div className="flex flex-wrap items-stretch gap-2">
        {steps.map((s, i) => (
          <div key={s.label} className="flex min-w-[150px] flex-1 items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${s.tone}`}>
              <s.icon className="h-4 w-4" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{s.label}</p>
              <p className="truncate text-lg font-bold leading-tight text-slate-900">{s.value}</p>
              {s.sub && <p className="truncate text-[10px] text-slate-500">{s.sub}</p>}
            </div>
            {i < steps.length - 1 && <ArrowRight className="ml-auto h-4 w-4 shrink-0 text-slate-300" aria-hidden="true" />}
          </div>
        ))}

        <div className={`flex min-w-[150px] flex-1 flex-col justify-center rounded-xl border p-3 text-center ${riskBg}`}>
          <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500">Transport risk</p>
          <p className={`text-xl font-bold capitalize ${riskTone}`}>{transport?.risk_level ?? '--'}</p>
          <p className="text-[10px] text-slate-500">score {fmt(transport?.risk_score ?? null, 0)}/100</p>
        </div>
      </div>

      {transport?.main_contributing_factors?.length ? (
        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          {transport.main_contributing_factors.map((f) => (
            <span key={f} className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-[11px] text-slate-600">
              {f}
            </span>
          ))}
        </div>
      ) : null}

      {transport?.disclaimer && <p className="mt-3 text-[11px] leading-relaxed text-slate-500">{transport.disclaimer}</p>}
    </section>
  )
}