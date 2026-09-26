import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, MapPin } from 'lucide-react'
import { getStations } from '../api/client'
import type { Station } from '../types'

/**
 * Station picker for the primary navigation.
 *
 * Every station is reachable from here, and selecting one carries it into the
 * Alerts view as a `?station=` filter so the operator lands on that station's
 * advisories instead of the network-wide feed. The list is fetched once and
 * shared through the session so switching menus does not re-request it.
 */
const CACHE_KEY = 'aerocast_station_names'
const CACHE_TTL_MS = 10 * 60 * 1000

interface CachedStations {
  names: string[]
  at: number
}

function readCache(): string[] | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as CachedStations
    if (!Array.isArray(parsed.names) || Date.now() - parsed.at > CACHE_TTL_MS) return null
    return parsed.names
  } catch {
    return null
  }
}

function writeCache(names: string[]): void {
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ names, at: Date.now() } satisfies CachedStations))
  } catch {
    // Storage unavailable (private mode) — the menu still works, just refetches.
  }
}

export function useStationNames(): { names: string[]; loading: boolean } {
  const [names, setNames] = useState<string[]>(() => readCache() ?? [])
  const [loading, setLoading] = useState(() => readCache() === null)

  useEffect(() => {
    if (names.length) return
    let cancelled = false
    getStations()
      .then((res) => {
        if (cancelled) return
        const list = (res.data as Station[]).map((s) => s.name).sort((a, b) => a.localeCompare(b))
        setNames(list)
        writeCache(list)
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [names.length])

  return { names, loading }
}

export default function StationsMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const { names, loading } = useStationNames()

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  function select(name: string) {
    setOpen(false)
    navigate(`/alerts?station=${encodeURIComponent(name)}`)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="nav-link items-center"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <MapPin className="h-4 w-4" aria-hidden="true" /> Stations
        <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      {open && (
        <div
          role="menu"
          aria-label="NCR monitoring stations"
          className="absolute left-0 top-full z-40 mt-1 max-h-96 w-60 overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
        >
          {loading && !names.length ? (
            <p className="px-4 py-2 text-sm text-slate-400">Loading stations…</p>
          ) : names.length ? (
            names.map((name) => (
              <button
                key={name}
                type="button"
                role="menuitem"
                onClick={() => select(name)}
                className="block w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-inst-50 hover:text-inst-800"
              >
                {name}
              </button>
            ))
          ) : (
            <p className="px-4 py-2 text-sm text-slate-400">Stations unavailable</p>
          )}
        </div>
      )}
    </div>
  )
}
