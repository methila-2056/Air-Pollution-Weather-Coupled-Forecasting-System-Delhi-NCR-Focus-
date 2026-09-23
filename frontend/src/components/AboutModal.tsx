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
  { name: 'CPCB', note: 'live air-quality observations / data.gov.in CKAN feed' },
  { name: 'Open-Meteo', note: 'weather and pressure-level atmospheric fields' },
  { name: 'NASA FIRMS', note: 'active fire detections (VIIRS hotspots)' },
  { name: 'ERA5 (Copernicus)', note: 'atmospheric reanalysis for the offline feature pipeline' },
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
            <ul className="space-y-1.5">
              {SOURCES.map((s) => (
                <li key={s.name} className="text-sm text-slate-700">
                  <span className="font-semibold text-slate-900">{s.name}</span>
                  <span className="text-slate-500"> — {s.note}</span>
                </li>
              ))}
            </ul>
          </div>

          <p className="text-xs leading-relaxed text-slate-500">
            Prototype developed for Smart India Hackathon 2026 — SIH26082. Not an official Government of India
            service.
          </p>
        </div>
      </div>
    </div>
  )
}