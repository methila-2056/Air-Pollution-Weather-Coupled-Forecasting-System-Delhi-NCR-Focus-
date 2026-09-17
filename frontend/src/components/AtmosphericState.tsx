import { Cloud, Factory, Layers, Mountain, Wind } from 'lucide-react'
import type { AtmosphereFeatures, StationAtmosphere } from '../types'
import { fmt, tsFmt } from '../lib/aqi'
import EmptyState from './EmptyState'

interface Props {
  atmosphere: StationAtmosphere | null
}

const DRIVERS: Array<{
  key: keyof AtmosphereFeatures
  icon: typeof Wind
  label: string
  value: (a: StationAtmosphere) => string
  sub: (a: StationAtmosphere) => string
  norm: (a: StationAtmosphere) => number | null
}> = [
  {
    key: 'wind', icon: Wind, label: 'Surface wind',
    value: (a) => `${fmt(a.wind.wind_speed_mps, 1)} m/s`,
    sub: (a) => `${a.wind.compass_from ?? '--'} · ${a.wind.label}`,
    norm: (a) => a.wind.normalized,
  },
  {
    key: 'pbl', icon: Cloud, label: 'Boundary layer',
    value: (a) => `${fmt(a.pbl.pbl_height_m)} m`,
    sub: (a) => a.pbl.label,
    norm: (a) => a.pbl.normalized,
  },
  {
    key: 'ventilation', icon: Factory, label: 'Ventilation',
    value: (a) => `${fmt(a.ventilation.ventilation_coefficient_m2s)} m²/s`,
    sub: (a) => a.ventilation.label,
    norm: (a) => a.ventilation.normalized,
  },
  {
    key: 'inversion', icon: Layers, label: 'Inversion',
    value: (a) => (a.inversion?.detected ? (a.inversion.category ?? 'Detected') : 'None'),
    sub: (a) => a.inversion?.dispersion_condition ?? 'No lapse-rate profile',
    norm: (a) => a.inversion?.normalized ?? null,
  },
  {
    key: 'trapping', icon: Mountain, label: 'Trapping',
    value: (a) => fmt(a.trapping.score, 2),
    sub: (a) => a.trapping.label,
    norm: (a) => a.trapping.normalized,
  },
]

function band(n: number | null): string {
  if (n == null) return '#cbd5e1'
  if (n >= 0.7) return '#dc2626'
  if (n >= 0.45) return '#d97706'
  return '#16a34a'
}

export default function AtmosphericState({ atmosphere }: Props) {
  if (!atmosphere) {
    return (
      <section className="card">
        <div className="card-header mb-4">Atmospheric state</div>
        <EmptyState
          title="Atmospheric profile unavailable"
          hint="Requires stored weather and pressure-level observations for this station."
        />
      </section>
    )
  }

  const norms = DRIVERS.map((d) => d.norm(atmosphere)).filter((v): v is number => v != null)
  const handicap = norms.length ? norms.reduce((s, v) => s + v, 0) / norms.length : null
  const pct = handicap != null ? Math.round(handicap * 100) : null
  const gaugeColor = pct == null ? '#cbd5e1' : pct >= 70 ? '#dc2626' : pct >= 45 ? '#d97706' : '#16a34a'

  return (
    <section className="card">
      <div className="mb-4 flex items-center justify-between gap-2">
        <h2 className="text-base font-bold text-slate-900">Atmospheric state</h2>
        <span className="rounded-full bg-inst-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-inst-800">
          Estimated · 0–1 normalised
        </span>
      </div>

      <div className="grid gap-6 md:grid-cols-[180px_1fr]">
        <div className="flex flex-col items-center justify-center gap-1 rounded-xl bg-slate-50 p-3">
          <svg viewBox="0 0 120 75" className="h-20 w-32" role="img" aria-label="Stagnation propensity gauge">
            <path d="M 10 62 A 50 50 0 0 1 110 62" fill="none" stroke="#e2e8f0" strokeWidth="11" strokeLinecap="round" />
            {pct != null && (
              <path
                d="M 10 62 A 50 50 0 0 1 110 62"
                fill="none"
                stroke={gaugeColor}
                strokeWidth="11"
                strokeLinecap="round"
                strokeDasharray={`${(pct / 100) * Math.PI * 50} ${Math.PI * 50}`}
              />
            )}
            <text x="60" y="60" textAnchor="middle" fontSize="20" fontWeight="700" fill={gaugeColor}>
              {pct ?? '--'}
            </text>
          </svg>
          <p className="text-sm font-semibold text-slate-700">Stagnation propensity</p>
          <p className="text-center text-[10px] leading-tight text-slate-500">higher = stronger dispersion constraint</p>
        </div>

        <div className="space-y-3">
          {DRIVERS.map((d) => {
            const n = d.norm(atmosphere)
            const Icon = d.icon
            return (
              <div key={d.key} className="flex items-center gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-inst-50">
                  <Icon className="h-4 w-4 text-inst-700" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="truncate text-xs font-medium text-slate-500">{d.label}</p>
                    <p className="whitespace-nowrap text-xs font-bold text-slate-900">{d.value(atmosphere)}</p>
                  </div>
                  <p className="truncate text-[10px] text-slate-500">{d.sub(atmosphere)}</p>
                  <div className="mt-1 h-1.5 w-full rounded-full bg-slate-200">
                    <div
                      className="h-1.5 rounded-full transition-all"
                      style={{ width: `${n != null ? Math.round(n * 100) : 0}%`, backgroundColor: band(n) }}
                    />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
        Drivers come from live station diagnostics; the aggregate is the mean of available normalised values and is
        labelled Estimated — it is not an official dispersion metric. Analysed {tsFmt(atmosphere.analyzed_at)} UTC.
      </p>
    </section>
  )
}