import { useState, useEffect, useCallback, useRef } from 'react'
import type { HistoryPoint, FetchState } from '../types'
import { INDEX_MAP } from '../types'

const BASE = '/api'

type IndexKey = keyof typeof INDEX_MAP

export function useHistory(
  indexKey: IndexKey,
  field: 'pe' | 'pb' = 'pe',
  years: number = 5
): FetchState<HistoryPoint[]> {
  const [state, setState] = useState<FetchState<HistoryPoint[]>>({
    data: null,
    loading: true,
    error: null,
  })
  const abortRef = useRef<AbortController | null>(null)

  const fetchHistory = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const code = INDEX_MAP[indexKey].code
      const res = await fetch(`${BASE}/history?index=${code}&field=${field}&years=${years}`, { signal: controller.signal })
      if (!res.ok) throw new Error(`API error: ${res.status}`)
      const json = await res.json()
      if (!controller.signal.aborted) setState({ data: json.data as HistoryPoint[], loading: false, error: null })
    } catch (err) {
      if (!controller.signal.aborted) setState({ data: null, loading: false, error: (err as Error).message })
    }
  }, [field, indexKey, years])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchHistory()
    return () => abortRef.current?.abort()
  }, [fetchHistory])

  return state
}
