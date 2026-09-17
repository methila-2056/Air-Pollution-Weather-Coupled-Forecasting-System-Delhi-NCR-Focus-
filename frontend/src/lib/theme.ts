// Single source of truth for chart and status colours used across the app.
// Brand tokens (lvinst-*/navy-*) live in tailwind.config.js — anything that must
// be consumed as a raw hex (Recharts, SVG gauges, Leaflet) lives here.

export const CHART = {
  brand: '#0B4F8A', // inst-700 — primary/forecast lines
  grid: '#e2e8f0',
  axis: '#64748b',
  tooltipBg: '#ffffff',
  tooltipBorder: '#e2e8f0',
  tooltipLabel: '#334155',
  naaqsPm25: '#d97706', // NAAQS 60 µg/m³ reference line
  noData: '#cbd5e1',
} as const

export const POLLUTANT_COLORS: Record<string, string> = {
  aqi: '#0B4F8A',
  pm25: '#dc2626',
  pm10: '#d97706',
  o3: '#059669',
  no2: '#7c3aed',
} as const

export function pollutantColor(key: string, fallback = CHART.brand): string {
  const base = key.replace(/_pred$/, '')
  return POLLUTANT_COLORS[base] ?? fallback
}

// Status ladder used by gauges, meters and bars:
// bad (#dc2626) -> warn (#d97706) -> good (#16a34a) -> muted/no data.
export const STATUS = {
  bad: '#dc2626',
  warn: '#d97706',
  good: '#16a34a',
  muted: '#cbd5e1',
} as const