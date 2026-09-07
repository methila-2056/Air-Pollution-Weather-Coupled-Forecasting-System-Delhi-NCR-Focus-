import { useState, useEffect, useCallback } from 'react'

interface UseApiState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    loading: true,
    error: null,
  })

  const refetch = useCallback(() => {
    setState({ data: null, loading: true, error: null })
    fetcher()
      .then(data => setState({ data, loading: false, error: null }))
      .catch((err: Error) =>
        setState({ data: null, loading: false, error: err.message || 'Failed to load data' })
      )
  }, deps)

  useEffect(() => { refetch() }, [refetch])

  return { ...state, refetch }
}
