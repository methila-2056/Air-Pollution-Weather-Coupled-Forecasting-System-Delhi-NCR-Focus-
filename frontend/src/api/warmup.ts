import { api } from './client'

// Render free-tier instances scale to zero after ~15 min idle. While any
// browser tab is open this pinger polls the (cheap) /system health endpoint
// every few minutes so the demo never hits a cold start mid-session. The
// ping only reads data and is fire-and-forget.
let started = false

const DEFAULT_INTERVAL_MS = 240_000

export function startKeepWarm(intervalMs: number = DEFAULT_INTERVAL_MS): void {
  if (started) return
  started = true
  const ping = () => {
    api.get('/system').catch(() => {
      // Backend sleeping or waking; the axios retry loop handles warming.
    })
  }
  ping()
  setInterval(ping, intervalMs)
}