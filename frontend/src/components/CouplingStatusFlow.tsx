import { useMemo, useState } from 'react'
import { ArrowDown, ArrowRight, CloudSun, Wind as WindIcon, Layers, FlaskConical, RefreshCcw, ChevronRight, Info } from 'lucide-react'
import type { CouplingData, CouplingFeaturesResponse } from '../types'

interface Props {
  data: CouplingData | null
  features: CouplingFeaturesResponse | null
}

type DirectionStatus = 'ACTIVE' | 'LIMITED' | 'UNAVAILABLE'

interface FlowNode {
  id: string
  icon: typeof CloudSun
  title: string
  subtitle: string
  vars: Array<[string, number | string | boolean | null | undefined, string, string]>
}

const STATUS_STYLE: Record<DirectionStatus, string> = {
  ACTIVE: 'bg-emerald-50 border-emerald-200 text-emerald-800',
  LIMITED: 'bg-amber-50 border-amber-200 text-amber-800',
  UNAVAILABLE: 'bg-slate-50 border-slate-200 text-slate-500',
}

function fmtVal(v: number | string | boolean | null | undefined, digits = 1) {
  if (v === null || v === undefined || v === '') return 'Unavailable'
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (typeof v === 'number') return Number.isNaN(v) ? 'Unavailable' : v.toFixed(digits)
  return String(v)
}

function statusChip(label: string, status: DirectionStatus, reason: string) {
  return (
    <div className={`rounded-xl border p-4 ${STATUS_STYLE[status]}`}>
      <div className="flex items-center gap-2">
        <ArrowDown className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span className="text-sm font-bold uppercase tracking-wide">{label}</span>
        <span className={`ml-auto rounded-full px-2.5 py-0.5 text-xs font-bold ${status === 'ACTIVE' ? 'bg-emerald-600 text-white' : status === 'LIMITED' ? 'bg-amber-500 text-white' : 'bg-slate-400 text-white'}`}>
          {status}
        </span>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed">{reason}</p>
    </div>
  )
}

export default function CouplingStatusFlow({ data, features }: Props) {
  const [selected, setSelected] = useState<string | null>(null)

  const metToPoll = useMemo<{ status: DirectionStatus; reason: string }>(() => {
    if (!features) {
      return {
        status: 'UNAVAILABLE',
        reason: 'No coupling-feature response for this station (stored weather/observations or the endpoint are unavailable).',
      }
    }
    const inputs = features.inputs ?? {}
    const hasWeather = inputs.wind_speed_mps != null || inputs.pbl_height_m != null || inputs.temperature_c != null
    if (!hasWeather) {
      return {
        status: 'UNAVAILABLE',
        reason: 'Meteorology inputs (wind / PBL height / temperature) are all unavailable for this station.',
      }
    }
    const quality = features.data_quality ?? 'GOOD'
    if (quality === 'GOOD') {
      return {
        status: 'ACTIVE',
        reason: 'All nine coupling features are computed from stored weather and fed into the forecasters (weather → pollution).',
      }
    }
    return {
      status: 'LIMITED',
      reason: `Coupling features computed from stored weather, but data quality is ${quality} — some features are unavailable.`,
    }
  }, [features])

  const pollToMet = useMemo<{ status: DirectionStatus; reason: string }>(() => {
    if (!data || !data.diag) {
      return {
        status: 'UNAVAILABLE',
        reason: 'No aerosol-feedback diagnostics available (coupling engine did not produce a stability response).',
      }
    }
    const idx = data.diag.stability_coupling_index ?? 0
    if (data.pm25 == null && idx <= 0) {
      return {
        status: 'LIMITED',
        reason: 'Feedback surrogate is present but current PM2.5 is unavailable, so the aerosol → meteorology term cannot be evaluated live.',
      }
    }
    return {
      status: 'ACTIVE',
      reason: `Aerosol proxy → radiation transmittance (${(data.diag.radiation_transmittance * 100).toFixed(0)}%) → PBL suppression (${(data.diag.pbl_suppression_factor * 100).toFixed(0)}%) → stability-coupling index (${idx.toFixed(3)}). ML-based two-way coupling surrogate, not physical WRF-Chem.`,
    }
  }, [data])

  const inputs = features?.inputs ?? {}
  const feat = features?.features ?? {}
  const diag = data?.diag

  const nodes = useMemo<FlowNode[]>(() => {
    return [
      {
        id: 'weather',
        icon: CloudSun,
        title: 'Weather',
        subtitle: 'Observed + NWP fields',
        vars: [
          ['Wind speed', inputs.wind_speed_mps, 'm/s', 'Stored weather (Open-Meteo) → coupling inputs'],
          ['Wind direction', inputs.wind_direction_deg, '°', 'Stored weather (Open-Meteo)'],
          ['Temperature', inputs.temperature_c, '°C', 'Stored weather (Open-Meteo)'],
          ['Humidity', inputs.humidity_pct, '%', 'Stored weather (Open-Meteo)'],
          ['Pressure', inputs.pressure_hpa, 'hPa', 'Stored weather (Open-Meteo)'],
          ['PBL height', inputs.pbl_height_m, 'm', 'Stored weather boundary_layer_height'],
          ['Inversion', inputs.inversion_detected, '', 'Lapse-rate / PBL-proxy detection'],
        ],
      },
      {
        id: 'dispersion',
        icon: WindIcon,
        title: 'Atmospheric state',
        subtitle: 'Dispersion & trapping',
        vars: [
          ['Dispersion potential', feat.dispersion_potential?.value, '0–1', feat.dispersion_potential?.basis ?? 'Coupling engine'],
          ['Accumulation potential', feat.accumulation_potential?.value, '0–1', feat.accumulation_potential?.basis ?? 'Coupling engine'],
          ['Inversion trapping', feat.inversion_trapping_potential?.value, '0–1', feat.inversion_trapping_potential?.basis ?? 'Coupling engine'],
          ['Stagnation index', feat.pollution_stagnation_index?.value, '0–1', feat.pollution_stagnation_index?.basis ?? 'Coupling engine'],
          ['Meteo–pollution interaction', feat.meteorology_pollution_interaction?.value, '0–1', 'Composite feedback-surrogate band'],
        ],
      },
      {
        id: 'pollutants',
        icon: Layers,
        title: 'Pollutants',
        subtitle: 'Observed + forecast',
        vars: [
          ['PM2.5 (observed)', inputs.pm25_ugm3, 'µg/m³', 'Stored CPCB observation'],
          ['PM10 (observed)', inputs.pm10_ugm3, 'µg/m³', 'Stored CPCB observation'],
          ['NO2 (observed)', inputs.no2_ugm3, 'µg/m³', 'Stored CPCB observation'],
          ['O3 (observed)', inputs.o3_ugm3, 'µg/m³', 'Stored CPCB observation'],
          ['72 h forecast', data?.pm25, 'µg/m³ anchor', 'Persistence / RF / XGBoost horizon models'],
        ],
      },
      {
        id: 'feedback',
        icon: FlaskConical,
        title: 'Aerosol feedback',
        subtitle: 'Pollution → meteorology proxy',
        vars: [
          ['Aerosol optical depth (est.)', diag?.aod_est, '', 'Aerosol-proxy estimate from stored PM2.5'],
          ['Radiation transmittance', diag ? diag.radiation_transmittance * 100 : null, '%', 'diminution from aerosol burden'],
          ['PBL suppression factor', diag ? diag.pbl_suppression_factor * 100 : null, '%', 'reduced vertical mixing from aerosol'],
          ['Coupling strength', diag?.coupling_strength, '', 'classify feedback states'],
        ],
      },
      {
        id: 'response',
        icon: RefreshCcw,
        title: 'Atmospheric response',
        subtitle: 'Next-step state',
        vars: [
          ['Corrected PBL height', diag?.corrected_pbl_height, 'm', 'PBL height after aerosol suppression'],
          ['Stability-coupling index', diag?.stability_coupling_index, '0–1', 'repository of the two-way feedback'],
          ['Feedback multiplier', diag ? (diag.feedback_multiplier ?? 0).toFixed(2) + '×' : null, '', '>1 = trapping reinforced'],
        ],
      },
    ]
  }, [features, data, inputs, feat, diag])

  const arrows = [
    { from: 'weather', to: 'dispersion', label: 'wind · PBLH · inversion · stability' },
    { from: 'dispersion', to: 'pollutants', label: 'ventilation · trapping · accumulation' },
    { from: 'pollutants', to: 'feedback', label: 'PM2.5 · PM10 (lagged)' },
    { from: 'feedback', to: 'response', label: 'AOD → transmittance → PBL suppression' },
  ]

  const nodeById = (id: string) => nodes.find((n) => n.id === id)
  const selectedNode = nodeById(selected ?? '')

  return (
    <div className="card">
      <h3 className="card-header">Coupling status — two-way weather ↔ pollution</h3>
      <p className="mb-4 text-xs text-slate-500">
        Directional availability is derived from the live backend: the coupling features payload
        (stored weather + observations → nine features) and the aerosol-feedback diagnostics of the
        <em> ML-based meteorology–pollution feedback surrogate</em>. This is not physical WRF-Chem.
      </p>

      <div className="grid gap-3 md:grid-cols-2">
        {statusChip('Meteorology → Pollution', metToPoll.status, metToPoll.reason)}
        {statusChip('Pollution → Meteorology', pollToMet.status, pollToMet.reason)}
      </div>

      <div className="mt-5">
        <p className="mb-3 text-sm font-semibold text-slate-700">Scientific flow (select a stage for variables & source)</p>
        <div className="grid gap-2 border-t border-slate-100 pt-4">
          {nodes.map((node) => {
            const Icon = node.icon
            const active = selected === node.id
            const downstream = arrows.find((a) => a.from === node.id)
            return (
              <div key={node.id}>
                <button
                  type="button"
                  onClick={() => setSelected(active ? null : node.id)}
                  aria-expanded={active}
                  className={`w-full rounded-xl border text-left transition-colors ${
                    active ? 'border-inst-500 bg-inst-50' : 'border-slate-200 bg-white hover:border-inst-300'
                  } px-4 py-3`}
                >
                  <div className="flex items-center gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-inst-700 text-white">
                      <Icon className="h-5 w-5" aria-hidden="true" />
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-slate-900">{node.title}</p>
                      <p className="text-xs text-slate-500">{node.subtitle}</p>
                    </div>
                    {downstream && (
                      <span className="ml-auto hidden items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600 sm:flex">
                        <ChevronRight className="h-3 w-3" aria-hidden="true" />
                        {downstream.label}
                      </span>
                    )}
                  </div>
                </button>
                {active && selectedNode && (
                  <div className="mt-2 overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                          <th className="py-1.5 pr-3">Variable</th>
                          <th className="py-1.5 pr-3 text-right">Current value</th>
                          <th className="py-1.5 text-right">Source / method</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedNode.vars.map(([k, v, unit, method]) => (
                          <tr key={k} className="border-b border-slate-100 last:border-0">
                            <td className="py-1.5 pr-3 font-medium text-slate-900">{k}</td>
                            <td className="py-1.5 pr-3 text-right text-slate-800">
                              {fmtVal(v)} {typeof v === 'number' ? unit : ''}
                            </td>
                            <td className="py-1.5 text-right text-xs text-slate-500">{method}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })}
        </div>
        <div className="mt-3 flex items-start gap-2 rounded-lg bg-slate-100 p-3 text-xs text-slate-600">
          <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-inst-700" aria-hidden="true" />
          <p>
            Arrow annotations are the actual variables linking each stage. Every value above is either a
            stored observation, an NWP/reanalysis field, or a documented 0..1 surrogate output (basis
            shown). Rows marked Unavailable mean the live data for this station is missing — never a
            fabricated replacement.
          </p>
        </div>
        {(features?.coupling_state || features?.data_quality) && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-inst-50 px-3 py-1 font-semibold text-inst-800">
              Coupling state: {features.coupling_state ?? 'n/a'}
            </span>
            <span className="rounded-full bg-inst-50 px-3 py-1 font-semibold text-inst-800">
              Domains: {features.coupling_domains ?? 'n/a'}
            </span>
            <span className="rounded-full bg-inst-50 px-3 py-1 font-semibold text-inst-800">
              Data quality: {features.data_quality ?? 'n/a'}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-slate-500">
              <Info className="h-3.5 w-3.5" aria-hidden="true" /> Surrogate — not a physical CTM.
            </span>
          </div>
        )}
      </div>
    </div>
  )
}