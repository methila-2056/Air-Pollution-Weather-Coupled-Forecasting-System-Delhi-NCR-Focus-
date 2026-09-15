export interface AqiStyle {
  label: string
  hex: string
  chip: string   // tailwind classes for badges (light theme)
  text: string   // tailwind text color
  bar: string    // solid background
}

// CPCB / MoEFCC air quality category thresholds (1-hour AQI, 8 pollutants).
export const AQI_CATEGORIES: Array<{ min: number; max: number } & AqiStyle> = [
  { min: 0, max: 50, label: 'Good', hex: '#16a34a', chip: 'bg-green-100 text-green-800 border-green-300', text: 'text-green-700', bar: 'bg-green-600' },
  { min: 51, max: 100, label: 'Satisfactory', hex: '#ca8a04', chip: 'bg-lime-100 text-lime-800 border-lime-300', text: 'text-lime-700', bar: 'bg-lime-500' },
  { min: 101, max: 200, label: 'Moderate', hex: '#d97706', chip: 'bg-amber-100 text-amber-800 border-amber-300', text: 'text-amber-700', bar: 'bg-amber-500' },
  { min: 201, max: 300, label: 'Poor', hex: '#dc2626', chip: 'bg-orange-100 text-orange-800 border-orange-300', text: 'text-orange-700', bar: 'bg-orange-600' },
  { min: 301, max: 400, label: 'Very Poor', hex: '#9333ea', chip: 'bg-red-100 text-red-800 border-red-300', text: 'text-red-700', bar: 'bg-red-700' },
  { min: 401, max: Infinity, label: 'Severe', hex: '#7f1d1d', chip: 'bg-red-200 text-red-900 border-red-400', text: 'text-red-900', bar: 'bg-red-900' },
]

export function aqiStyle(aqi: number | null | undefined): AqiStyle {
  if (typeof aqi !== 'number' || Number.isNaN(aqi)) {
    return { label: 'No data', hex: '#94a3b8', chip: 'bg-slate-100 text-slate-500 border-slate-200', text: 'text-slate-400', bar: 'bg-slate-300' }
  }
  return AQI_CATEGORIES.find((c) => aqi >= c.min && aqi <= c.max) ?? AQI_CATEGORIES[5]
}

export function aqiCategory(aqi: number | null | undefined, fallback = 'No data'): string {
  if (typeof aqi !== 'number' || Number.isNaN(aqi)) return fallback
  return aqiStyle(aqi).label
}

export function fmt(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  return v.toFixed(digits)
}

export function tsFmt(s: string | null | undefined, showSeconds = false): string {
  if (!s) return '--'
  const cleaned = s.endsWith('Z') || s.includes('+00:00') ? s : `${s}Z`
  const d = new Date(cleaned)
  if (Number.isNaN(d.getTime())) return s.replace('T', ' ').slice(0, 16)
  return d
    .toISOString()
    .replace('T', ' ')
    .slice(0, showSeconds ? 19 : 16)
}