import { AlarmClock } from 'lucide-react'
import type { ForecastPoint } from '../types'
import { aqiStyle, fmt } from '../lib/aqi'
import EmptyState from './EmptyState'

interface Props {
  forecast: ForecastPoint[] | null
}

export default function ForecastRiskBand({ forecast }: Props) {
  const valid = (forecast ?? []).filter((f) => f.aqi_pred != null && f.aqi_pred > 0)
  if (!valid.length) {
    return (
      <section className="card">
        <div className="card-header mb-4">72-hour risk band</div>
        <EmptyState title="No forecast stored" hint="Persisted 72-hour forecasts for this station have not been generated yet." />
      </section>
    )
  }

  const buckets = [
    { range: 'Now – 24h', from: 0, to: 24 },
    { range: '24 – 48h', from: 24, to: 48 },
    { range: '48 – 72h', from: 48, to: 72 },
  ]

  const worst = buckets.map((b) => {
    const pts = valid.filter((f) => f.horizon_hours >= b.from && f.horizon_hours < b.to)
    const peak = pts.reduce<ForecastPoint | null>(
      (acc, p) => (acc == null || (p.aqi_pred ?? 0) > (acc.aqi_pred ?? 0) ? p : acc),
      null,
    )
    return { ...b, peak }
  })

  const overallPeak = valid.reduce<ForecastPoint | null>(
    (acc, p) => (acc == null || (p.aqi_pred ?? 0) > (acc.aqi_pred ?? 0) ? p : acc),
    null,
  )
  const peakStyle = aqiStyle(overallPeak?.aqi_pred ?? null)

  return (
    <section className="card">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <AlarmClock className="h-4 w-4 text-inst-700" aria-hidden="true" />
          <h2 className="text-base font-bold text-slate-900">72-hour risk band</h2>
          <span className="rounded-full bg-inst-50 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-inst-800">
            Estimated outlook
          </span>
        </div>
        {overallPeak && (
          <p className="text-xs text-slate-600">
            Peak <b className={peakStyle.text}>AQI {fmt(overallPeak.aqi_pred, 0)} ({peakStyle.label})</b> at +{overallPeak.horizon_hours}h
          </p>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3">
        {worst.map((b) => {
          const style = aqiStyle(b.peak?.aqi_pred ?? null)
          const height = b.peak?.aqi_pred != null ? Math.max(16, Math.min(100, (b.peak.aqi_pred / 400) * 100)) : 12
          return (
            <div key={b.range} className="flex flex-col items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{b.range}</p>
              <div className="flex h-24 w-full items-end overflow-hidden rounded-lg bg-white p-1">
                <div
                  className="w-full rounded-md transition-all"
                  style={{ height: `${height}%`, backgroundColor: b.peak ? style.hex : '#cbd5e1' }}
                />
              </div>
              {b.peak ? (
                <p className="text-sm font-bold text-slate-900">
                  AQI {fmt(b.peak.aqi_pred, 0)} · <span className={`capitalize ${style.text}`}>{style.label}</span>
                </p>
              ) : (
                <p className="text-sm text-slate-400">No points</p>
              )}
            </div>
          )
        })}
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-slate-500">
        Segments show the peak predicted AQI per window from the persisted 72-hour ML forecast; band colour follows the
        CPCB category of that peak.
      </p>
    </section>
  )
}