import type { ForecastPoint } from '../types'

function tsMs(s: string | null | undefined): number {
  if (!s) return 0
  const cleaned = s.endsWith('Z') || s.includes('+') ? s : `${s}Z`
  const t = new Date(cleaned).getTime()
  return Number.isNaN(t) ? 0 : t
}

/**
 * Reduce a raw list of persisted forecast rows (which contains one entry per
 * horizon for EVERY forecast run since seeding) to the single most recent
 * run — one row per horizon, so stale outlier runs never dominate the outlook.
 */
export function latestForecastRun(rows: readonly ForecastPoint[] | null | undefined): ForecastPoint[] {
  const byHorizon = new Map<number, ForecastPoint>()
  for (const r of rows ?? []) {
    const cur = byHorizon.get(r.horizon_hours)
    if (!cur || tsMs(r.timestamp) >= tsMs(cur.timestamp)) {
      byHorizon.set(r.horizon_hours, r)
    }
  }
  return Array.from(byHorizon.values()).sort((a, b) => a.horizon_hours - b.horizon_hours)
}