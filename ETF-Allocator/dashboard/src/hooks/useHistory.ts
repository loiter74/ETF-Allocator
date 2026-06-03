import { useState, useEffect, useCallback } from 'react'
import type { HistoryPoint, FetchState } from '../types'
import { INDEX_MAP } from '../types'

const BASE = '/api'

type IndexKey = keyof typeof INDEX_MAP

export function useHistory(
  indexKey: IndexKey,
  field: 'pe' | 'pb' = 'pe',
  years: number = 5
): FetchState<HistoryPoint[]> & { setIndex: (key: IndexKey) => void } {
  const [currentIndex, setCurrentIndex] = useState<IndexKey>(indexKey)
  const [state, setState] = useState<FetchState<HistoryPoint[]>>({
    data: null,
    loading: true,
    error: null,
  })

  const fetchHistory = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const code = INDEX_MAP[currentIndex].code
      const res = await fetch(`${BASE}/history?index=${code}&field=${field}&years=${years}`)
      if (!res.ok) throw new Error(`API error: ${res.status}`)
      const json = await res.json()
      setState({ data: json.data as HistoryPoint[], loading: false, error: null })
    } catch (err) {
      setState({ data: null, loading: false, error: (err as Error).message })
    }
  }, [currentIndex, field, years])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchHistory()
  }, [fetchHistory])

  return { ...state, setIndex: setCurrentIndex }
}
