import { useEffect, useRef } from 'react'

/**
 * Call a refresh callback on an interval while the page is visible.
 * The interval is not started until `enabled` is true and is paused in
 * background tabs to avoid needless polling.
 */
export function useIntervalRefresh(
  onRefresh: () => void,
  intervalMs: number,
  enabled = true,
) {
  const callbackRef = useRef(onRefresh)
  callbackRef.current = onRefresh

  useEffect(() => {
    if (!enabled) return
    let timer: ReturnType<typeof setInterval> | undefined

    const tick = () => {
      if (document.visibilityState === 'visible') {
        callbackRef.current()
      }
    }

    timer = setInterval(tick, intervalMs)
    return () => {
      if (timer) clearInterval(timer)
    }
  }, [intervalMs, enabled])
}