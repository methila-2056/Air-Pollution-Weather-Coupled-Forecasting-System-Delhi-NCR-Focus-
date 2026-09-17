import { BookOpen } from 'lucide-react'
import type { StationAtmosphere } from '../types'
import { fmt, tsFmt } from '../lib/aqi'
import EmptyState from './EmptyState'

interface Props {
  atmosphere: StationAtmosphere | null
}

export default function AtmosphericStory({ atmosphere }: Props) {
  if (!atmosphere) {
    return (
      <section className="card">
        <div className="card-header mb-4">Atmospheric story</div>
        <EmptyState
          title="No atmospheric profile"
          hint="Requires stored weather and pressure-level observations for this station."
        />
      </section>
    )
  }

  const sentences: string[] = []

  const w = atmosphere.wind
  if (w.wind_speed_mps != null) {
    sentences.push(
      w.wind_direction_deg != null
        ? `${w.compass_from ?? `${w.wind_direction_deg}°`} winds at ${fmt(w.wind_speed_mps, 1)} m/s — classified as ${w.label.toLowerCase()}.`
        : `Winds at ${fmt(w.wind_speed_mps, 1)} m/s — classified as ${w.label.toLowerCase()}.`,
    )
  }

  if (atmosphere.pbl.pbl_height_m != null) {
    sentences.push(`The boundary layer sits at ${fmt(atmosphere.pbl.pbl_height_m)} m (${atmosphere.pbl.label.toLowerCase()}) — the mixing depth available to dilute surface emissions.`)
  }

  if (atmosphere.ventilation.ventilation_coefficient_m2s != null) {
    sentences.push(`Ventilation is ${fmt(atmosphere.ventilation.ventilation_coefficient_m2s)} m²/s (${atmosphere.ventilation.label.toLowerCase()}): it sets how readily pollutants are flushed from the region.`)
  }

  const inv = atmosphere.inversion
  if (inv) {
    if (inv.detected) {
      sentences.push(
        `A ${inv.category?.toLowerCase() ?? 'temperature'} inversion is capping the surface layer${
          inv.base_pressure_hpa ? ` near ${inv.base_pressure_hpa} hPa` : ''
        }, so ${inv.dispersion_condition?.toLowerCase() ?? 'vertical dispersion is restricted'}.`,
      )
    } else {
      sentences.push('No temperature inversion is detected in the vertical profile, leaving dispersion comparatively open.')
    }
  }

  sentences.push(`Combined trapping risk is ${atmosphere.trapping.label.toLowerCase()} (score ${fmt(atmosphere.trapping.score, 2)}).`)

  return (
    <section className="card">
      <div className="mb-3 flex items-center gap-2">
        <BookOpen className="h-4 w-4 text-inst-700" aria-hidden="true" />
        <h2 className="text-base font-bold text-slate-900">Atmospheric story</h2>
        <span className="ml-auto rounded-full bg-inst-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-inst-800">
          Estimated narrative
        </span>
      </div>
      <div className="space-y-2 text-sm leading-relaxed text-slate-700">
        {sentences.map((s, i) => (
          <p key={i}>{s}</p>
        ))}
      </div>
      <p className="mt-3 text-[11px] text-slate-500">
        Narrative composed from live station diagnostics · analysed {tsFmt(atmosphere.analyzed_at)}.
      </p>
    </section>
  )
}