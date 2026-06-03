import { useState, useEffect, useCallback } from 'react'
import type { MonthlyReport, SimulateRequest, SimulateResponse, FetchState } from '../types'

const BASE = '/api'

export function useReport(date: string): FetchState<MonthlyReport> & { refetch: () => void } {
  const [state, setState] = useState<FetchState<MonthlyReport>>({
    data: null,
    loading: true,
    error: null,
  })

  const fetchReport = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const res = await fetch(`${BASE}/report?date=${encodeURIComponent(date)}`)
      if (!res.ok) throw new Error(`API error: ${res.status}`)
      const json: MonthlyReport = await res.json()
      setState({ data: json, loading: false, error: null })
    } catch (err) {
      setState({ data: null, loading: false, error: (err as Error).message })
    }
  }, [date])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchReport()
  }, [fetchReport])

  return { ...state, refetch: fetchReport }
}

export function useSimulate() {
  const [state, setState] = useState<FetchState<SimulateResponse>>({
    data: null,
    loading: false,
    error: null,
  })

  const simulate = async (body: SimulateRequest) => {
    setState({ data: null, loading: true, error: null })
    try {
      const res = await fetch(`${BASE}/report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`API error: ${res.status}`)
      const json: SimulateResponse = await res.json()
      setState({ data: json, loading: false, error: null })
    } catch (err) {
      setState({ data: null, loading: false, error: (err as Error).message })
    }
  }

  return { ...state, simulate }
}
