import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  InvestmentCreateRequest,
  InvestmentResponse,
} from '../types';

const ENDPOINT = '/api/investments';

async function apiError(response: Response): Promise<string> {
  try {
    const payload: unknown = await response.json();
    if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
      const detail = (payload as { detail?: unknown }).detail;
      if (typeof detail === 'string') return detail;
    }
  } catch {
    // Fall back to the HTTP status below when the body is not JSON.
  }
  return `请求失败 (${response.status})`;
}

export function useInvestmentRecords() {
  const [data, setData] = useState<InvestmentResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fetchAbortRef = useRef<AbortController | null>(null);

  const refetch = useCallback(async () => {
    fetchAbortRef.current?.abort();
    const controller = new AbortController();
    fetchAbortRef.current = controller;
    setLoading(true);
    try {
      const response = await fetch(ENDPOINT, { signal: controller.signal });
      if (!response.ok) throw new Error(await apiError(response));
      const payload: InvestmentResponse = await response.json();
      if (!controller.signal.aborted) {
        setData(payload);
        setError(null);
      }
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : '投入记录加载失败');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refetch();
    return () => fetchAbortRef.current?.abort();
  }, [refetch]);

  const createRecord = useCallback(async (record: InvestmentCreateRequest): Promise<boolean> => {
    setSaving(true);
    setError(null);
    try {
      const response = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(record),
      });
      if (!response.ok) throw new Error(await apiError(response));
      await refetch();
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '投入记录保存失败');
      return false;
    } finally {
      setSaving(false);
    }
  }, [refetch]);

  const deleteRecord = useCallback(async (recordId: number): Promise<boolean> => {
    setDeletingId(recordId);
    setError(null);
    try {
      const response = await fetch(`${ENDPOINT}/${recordId}`, { method: 'DELETE' });
      if (!response.ok) throw new Error(await apiError(response));
      await refetch();
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '投入记录删除失败');
      return false;
    } finally {
      setDeletingId(null);
    }
  }, [refetch]);

  return {
    data,
    loading,
    saving,
    deletingId,
    error,
    refetch,
    createRecord,
    deleteRecord,
  };
}
