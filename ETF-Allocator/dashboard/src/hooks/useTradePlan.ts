import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  FetchState,
  TradePlanPreviewRequest,
  TradePlanPreviewResponse,
} from '../types';

function apiErrorMessage(payload: unknown, status: number): string {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map(item => (
          typeof item === 'object' && item !== null && 'msg' in item
            ? String((item as { msg: unknown }).msg)
            : String(item)
        ))
        .join('；');
    }
  }
  return `交易计划接口返回 ${status}`;
}

export function useTradePlanPreview() {
  const [state, setState] = useState<FetchState<TradePlanPreviewResponse>>({
    data: null,
    loading: false,
    error: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  const preview = useCallback(async (body: TradePlanPreviewRequest) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState(current => ({ ...current, loading: true, error: null }));

    try {
      const response = await fetch('/api/trade-plan/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(apiErrorMessage(payload, response.status));
      if (!controller.signal.aborted) {
        setState({
          data: payload as TradePlanPreviewResponse,
          loading: false,
          error: null,
        });
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setState({ data: null, loading: false, error: (error as Error).message });
      }
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState({ data: null, loading: false, error: null });
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  return { ...state, preview, reset };
}
