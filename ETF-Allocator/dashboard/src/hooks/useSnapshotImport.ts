import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  FetchState,
  SnapshotImportRequest,
  SnapshotImportResponse,
  SnapshotOcrConfig,
} from '../types';

const DEFAULT_CONFIG: SnapshotOcrConfig = {
  deepseek_enabled: false,
  structuring_provider: 'local_parser',
  model: null,
  image_upload: false,
  ocr_location: 'browser',
  accepted_image_types: ['image/png', 'image/jpeg', 'image/webp'],
  max_files: 3,
  max_file_bytes: 8 * 1024 * 1024,
  max_total_bytes: 20 * 1024 * 1024,
  max_segment_characters: 30_000,
  max_total_characters: 60_000,
  privacy_notice: '原图仅在浏览器本地 OCR；服务端只接收识别文字。',
};

function errorMessage(payload: unknown, status: number): string {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return `截图解析接口返回 ${status}`;
}

export function useSnapshotImport() {
  const [config, setConfig] = useState<SnapshotOcrConfig>(DEFAULT_CONFIG);
  const [state, setState] = useState<FetchState<SnapshotImportResponse>>({
    data: null,
    loading: false,
    error: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetch('/api/portfolio-snapshot/ocr-config', { signal: controller.signal })
      .then(async response => {
        const payload = await response.json().catch(() => null);
        if (response.ok && payload && typeof payload === 'object') {
          setConfig(current => ({ ...current, ...(payload as Partial<SnapshotOcrConfig>) }));
        }
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  const parseText = useCallback(async (body: SnapshotImportRequest) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState(current => ({ ...current, loading: true, error: null }));
    try {
      const response = await fetch('/api/portfolio-snapshot/parse-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      const payload: unknown = await response.json().catch(() => null);
      if (!response.ok) throw new Error(errorMessage(payload, response.status));
      if (!controller.signal.aborted) {
        setState({ data: payload as SnapshotImportResponse, loading: false, error: null });
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setState({ data: null, loading: false, error: (error as Error).message });
      }
    }
  }, []);

  const setData = useCallback((data: SnapshotImportResponse) => {
    setState({ data, loading: false, error: null });
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);
  return { ...state, config, parseText, setData };
}
