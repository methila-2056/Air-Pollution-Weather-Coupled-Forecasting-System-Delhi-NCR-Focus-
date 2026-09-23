import { useEffect } from 'react'
import { Cpu, CloudSun, Database, Flame, Gauge, Info, Map, Sparkles, Wind, X } from 'lucide-react'

interface AboutModalProps {
  open: boolean
  onClose: () => void
}

const FEATURES = [
  { icon: Gauge, label: '72-hour PM2.5/AQI forecasting with hourly uncertainty bands' },
  { icon: Cpu, label: 'Multi-model ML ensemble — GRU, Random Forest, XGBoost' },
  { icon: Database, label: 'Near-real-time CPCB observational ingestion' },
  { icon: Map, label: 'Delhi NCR regional mapping & station-wise AQI tracking' },
  { icon: CloudSun, label: 'Atmospheric state insight — inversion, wind, temperature, humidity' },
  { icon: Flame, label: 'Regional stubble-fire detection (NASA FIRMS)' },
  { icon: Wind, label: 'Fire-plume transport & dispersion outlook' },
  { icon: Sparkles, label: 'Forecast explainability & model verification' },
]

const SOURCES = [
  { name: 'CPCB', note: 'live air-quality observations / data.gov.in CKAN feed', use: 'AQI, PM2.5/PM10/O3/NO2 training + live status', freq: 'hourly' },
  { name: 'Open-Meteo', note: 'surface + 1000/925/850/700 hPa pressure-level forecast fields', use: 'weather, PBL height, lapse-rate inversion analysis', freq: 'hourly' },
  { name: 'NASA FIRMS', note: 'active fire detections (VIIRS hotspots + FRP)', use: 'stubble-fire alerts, transport-risk estimation', freq: '3 h' },
  { name: 'ERA5 (Copernicus)', note: 'atmospheric reanalysis (offline only)', use: 'offline feature pipeline / model training window', freq: 'archival' },
]

const LIMITATIONS = [
  'Air-quality forecasts are ML-driven estimates with explicit per-hour uncertainty — never actual measurements.',
  'The "meteorology–pollution coupling" and "regional fire transport" modules are transparent data-driven heuristics/surrogates, not physics-based WRF-Chem chemistry-transport simulations.',
  'WRF-Chem is not executed by this prototype; the adapter purposely reports unavailable and is present so a real CTM run can be swapped in.',
  'Inversion strength is derived from the vertical lapse rate where stored pressure-levels exist; otherwise a clearly-labelled PBL-height proxy is used.',
  'Observed pollution is never overwritten by any formula serving the dashboards; missing data renders as "Data unavailable", never as filler.',
  'Crop-residue fires are tracked via satellite radiance; low FRP/confidence detections can be missed, and no direct source-verification to any specific farm is claimed.',
]

export default function AboutModal({ open, onClose }: AboutModalProps) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="About AeroCast-NCR"
      className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-900/50 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-xl bg-white shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 bg-inst-800 px-6 py-5 text-white">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Info className="h-5 w-5 text-cyan-300" aria-hidden="true" />
              <h2 className="text-lg font-bold uppercase tracking-wide">About AeroCast-NCR</h2>
            </div>
            <p className="mt-1 text-xs text-inst-100">National Air Quality Forecasting Unit · Delhi NCR</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-lg p-1.5 text-inst-100 transition-colors hover:bg-white/10 hover:text-white"
            aria-label="Close about panel"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-5 overflow-y-auto overscroll-contain px-6 py-5">
          <div>
            <span className="mb-2 inline-block rounded-full border border-inst-200 bg-inst-50 px-3 py-1 text-xs font-semibold text-inst-800">
              SIH 2026 · Problem Statement SIH26082
            </span>
            <p className="text-sm leading-relaxed text-slate-700">
              AeroCast-NCR is a prototype coupled air-quality–weather forecasting platform for the Delhi NCR region.
              Live and archived CPCB observations, Open-Meteo weather fields and NASA FIRMS fire detections feed a
              multi-model ML forecast pipeline. GRU, Random Forest and XGBoost horizon models produce 72-hour PM2.5
              and AQI outlooks with per-hour uncertainty bands, while ERA5-based reanalysis backs the offline
              atmospheric feature pipeline.
            </p>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-bold text-slate-900">Key features</h3>
            <ul className="space-y-1.5">
              {FEATURES.map(({ icon: Icon, label }) => (
                <li key={label} className="flex items-start gap-2 text-sm text-slate-700">
                  <Icon className="mt-0.5 h-4 w-4 shrink-0 text-inst-700" aria-hidden="true" />
                  <span>{label}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <h3 className="mb-2 text-sm font-bold text-slate-900">Data sources</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-300 text-left text-slate-500">
                    <th className="py-1 pr-3 font-semibold">Source</th>
                    <th className="py-1 pr-3 font-semibold">Used for</th>
                    <th className="py-1 font-semibold">Frequency</th>
                  </tr>
                </thead>
                <tbody>
                  {SOURCES.map((s) => (
                    <tr key={s.name} className="border-b border-slate-200 last:border-0 align-top">
                      <td className="py-1.5 pr-3">
                        <span className="font-semibold text-slate-900">{s.name}</span>
                        <span className="block text-[10px] leading-snug text-slate-500">{s.note}</span>
                      </td>
                      <td className="py-1.5 pr-3 text-slate-700">{s.use}</td>
                      <td className="py-1.5 text-slate-500">{s.freq}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
            <h3 className="mb-2 text-sm font-bold text-amber-900">Scientific limitations</h3>
            <ul className="list-inside list-disc space-y-1.5 text-xs leading-relaxed text-amber-900/90">
              {LIMITATIONS.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </div>

          <p className="text-xs leading-relaxed text-slate-500">
            Prototype developed for Smart India Hackathon 2026 — SIH26082. WRF-Chem interface, ERA5 fallback and
            data-driven coupling surrogates are included to indicate production-scale upgrade paths; this dashboard
            is not an official Government of India service.
          </p>
        </div>
      </div>
    </div>
  )
}