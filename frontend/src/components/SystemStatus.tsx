import { useEffect, useState } from 'react'
import { getSummary } from '../api/client'
import { useIntervalRefresh } from '../hooks/useIntervalRefresh'
import { fmt, tsFmt } from '../lib/aqi'
import type { SummaryResponse } from '../types'

interface Props {
  className?: string
}

export default function SystemStatus({ className = '' }: Props) {
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [offline, setOffline] = useState(false)

  const load = () => {
    getSummary()
      .then((r) => {
        setSummary(r.data)
        setOffline(false)
      })
      .catch(() => setOffline(true))
  }

  useEffect(() => { load() }, [])
  useIntervalRefresh(load, 60_000, true)

  let stale = false
  if (!offline && summary?.generated_at) {
    const t = new Date(summary.generated_at).getTime()
    if (!Number.isNaN(t)) stale = Date.now() - t > 2 * 60 * 60 * 1000
  }

  const dot = offline ? 'bg-red-500' : stale ? 'bg-amber-400' : 'bg-emerald-400'

  return (
    <div className={`hidden items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-xs text-white lg:flex ${className}`}>
      <span className="relative flex h-2 w-2">
        {!offline && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${dot}`} />}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dot}`} />
      </span>
      <span className="font-semibold uppercase tracking-wide">
        {offline ? 'API offline' : stale ? 'Data stale' : 'Live'}
      </span>
      {!offline && summary && (
        <span className="text-blue-100">
          NCR AQI {fmt(summary.ncr_avg_aqi, 0)} · {summary.stations_with_readings}/{summary.stations} stations · {tsFmt(summary.generated_at)}
        </span>
      )}
    </div>
  )
}