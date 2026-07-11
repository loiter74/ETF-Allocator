import { useState, useEffect, useCallback, useRef } from 'react'
import type { MonthlyReport, SimulateRequest, SimulateResponse, FetchState } from '../types'

const BASE = '/api'

export function useReport(date: string): FetchState<MonthlyReport> & { refetch: () => void } {
  const [state, setState] = useState<FetchState<MonthlyReport>>({
    data: null,
    loading: true,
    error: null,
  })
  const abortRef = useRef<AbortController | null>(null)

  const fetchReport = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const res = await fetch(`${BASE}/report?date=${encodeURIComponent(date)}`, { signal: controller.signal })
      if (!res.ok) throw new Error(`API error: ${res.status}`)
      const json: MonthlyReport = await res.json()
      if (!controller.signal.aborted) setState({ data: json, loading: false, error: null })
    } catch (err) {
      if (!controller.signal.aborted) setState({ data: null, loading: false, error: (err as Error).message })
    }
  }, [date])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchReport()
    return () => abortRef.current?.abort()
  }, [fetchReport])

  return { ...state, refetch: fetchReport }
}

export function useSimulate() {
  const [state, setState] = useState<FetchState<SimulateResponse>>({
    data: null,
    loading: false,
    error: null,
  })
  const abortRef = useRef<AbortController | null>(null)

  const simulate = useCallback(async (body: SimulateRequest) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setState({ data: null, loading: true, error: null })
    try {
      const res = await fetch(`${BASE}/report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(`API error: ${res.status}`)
      const json: SimulateResponse = await res.json()
      if (!controller.signal.aborted) setState({ data: json, loading: false, error: null })
    } catch (err) {
      if (!controller.signal.aborted) setState({ data: null, loading: false, error: (err as Error).message })
    }
  }, [])

  useEffect(() => () => abortRef.current?.abort(), [])

  return { ...state, simulate }
}
