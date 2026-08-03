import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { recognizeBrokerScreenshots } from '../lib/browserOcr';
import type { SnapshotImportResponse, SnapshotOcrConfig } from '../types';
import { BrokerScreenshotImport } from './BrokerScreenshotImport';

vi.mock('../lib/browserOcr', () => ({
  recognizeBrokerScreenshots: vi.fn(),
}));

const config: SnapshotOcrConfig = {
  deepseek_enabled: true,
  structuring_provider: 'deepseek',
  model: 'deepseek-v4-flash',
  image_upload: false,
  ocr_location: 'browser',
  accepted_image_types: ['image/png', 'image/jpeg', 'image/webp'],
  max_files: 3,
  max_file_bytes: 8 * 1024 * 1024,
  max_total_bytes: 20 * 1024 * 1024,
  max_segment_characters: 30_000,
  max_total_characters: 60_000,
  privacy_notice: '原图仅在浏览器本地 OCR',
};

const field = <T extends number | string>(value: T | null, confidence = 0.9, source = 'deepseek') => ({
  value,
  confidence: value == null ? 0 : confidence,
  source: value == null ? 'missing' : source,
  evidence: '科创50ETF 588000 600 1.04 0.80 624',
  value_date: null,
});

function importResponse(): SnapshotImportResponse {
  return {
    provider: 'deepseek',
    model: 'deepseek-v4-flash',
    input_characters: 42,
    read_only: true,
    image_uploaded: false,
    warnings: [],
    draft: {
      snapshot_date: field('2026-08-02'),
      account_cash: field(2272, 0.7),
      positions: [{
        asset: field('科创50ETF'),
        code: field('588000'),
        shares: field(600),
        price: field(1.04),
        average_cost: field(0.8),
        market_value: field(624),
        is_equity: true,
        warnings: [],
      }],
    },
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.mocked(recognizeBrokerScreenshots).mockReset();
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:preview') });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
});

describe('BrokerScreenshotImport', () => {
  it('keeps the image local, sends only OCR text, and applies only after confirmation', async () => {
    const response = importResponse();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
      if (String(input).includes('ocr-config')) return jsonResponse(config);
      if (String(input).includes('parse-text')) return jsonResponse(response);
      return jsonResponse({}, 404);
    });
    vi.mocked(recognizeBrokerScreenshots).mockImplementation(async (_files, onProgress) => {
      onProgress({ fileIndex: 0, fileCount: 1, fileName: 'broker.png', status: '完成', progress: 1 });
      return [{ name: 'broker.png', text: '科创50ETF 588000 持仓份额600 现价1.04 平均成本0.8', ocr_confidence: 91 }];
    });
    const onApply = vi.fn();
    render(<BrokerScreenshotImport snapshotDate="2026-08-02" onApply={onApply} />);

    const file = new File(['not-uploaded'], 'broker.png', { type: 'image/png' });
    fireEvent.change(screen.getByLabelText('选择券商截图'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: '识别并整理' }));

    expect(await screen.findByTestId('snapshot-import-review')).toBeInTheDocument();
    expect(onApply).not.toHaveBeenCalled();
    expect(screen.getByDisplayValue('600')).toBeInTheDocument();
    expect(screen.getByText(/DeepSeek · deepseek-v4-flash/)).toBeInTheDocument();

    const parseCall = fetchMock.mock.calls.find(call => String(call[0]).includes('parse-text'));
    const body = JSON.parse((parseCall?.[1] as RequestInit).body as string);
    expect(body.ocr_texts[0].text).toContain('持仓份额600');
    expect(JSON.stringify(body)).not.toContain('not-uploaded');
    expect(JSON.stringify(body)).not.toContain('data:image');

    fireEvent.change(screen.getByLabelText('识别账户现金'), { target: { value: '2300' } });
    fireEvent.click(screen.getByRole('button', { name: '应用到持仓快照' }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({
      account_cash: expect.objectContaining({ value: 2300, source: 'user' }),
    }));
    expect(screen.getByRole('status')).toHaveTextContent('尚未扫描交易计划');
    expect(fetchMock.mock.calls.some(call => String(call[0]).includes('trade-plan'))).toBe(false);
  });

  it('rejects a non-image before OCR or API parsing', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(config));
    render(<BrokerScreenshotImport snapshotDate="2026-08-02" onApply={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('选择券商截图'), {
      target: { files: [new File(['x'], 'positions.txt', { type: 'text/plain' })] },
    });

    expect(screen.getByRole('alert')).toHaveTextContent('格式不支持');
    await waitFor(() => expect(recognizeBrokerScreenshots).not.toHaveBeenCalled());
  });

  it('can structure pasted OCR text when browser OCR is unavailable', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => (
      String(input).includes('parse-text') ? jsonResponse(importResponse()) : jsonResponse(config)
    ));
    render(<BrokerScreenshotImport snapshotDate="2026-08-02" onApply={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('OCR文字'), { target: { value: '科创50ETF 持仓份额 600' } });
    fireEvent.click(screen.getByRole('button', { name: '整理粘贴文字' }));

    expect(await screen.findByTestId('snapshot-import-review')).toBeInTheDocument();
    expect(recognizeBrokerScreenshots).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls.some(call => String(call[0]).includes('parse-text'))).toBe(true);
  });

  it('blocks application when market value contradicts shares times price', async () => {
    const response = importResponse();
    response.draft.account_cash = field(1000);
    response.draft.positions.push({
      asset: field('航民股份'), code: field<string>(null),
      shares: field(100), price: field(0.69), average_cost: field(0.74), market_value: field(6069),
      is_equity: true, warnings: ['航民股份识别市值与份额×现价相差99%'],
    });
    response.warnings.push('航民股份识别市值与份额×现价相差99%');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async input => (
      String(input).includes('parse-text') ? jsonResponse(response) : jsonResponse(config)
    ));
    render(<BrokerScreenshotImport snapshotDate="2026-08-02" onApply={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('OCR文字'), { target: { value: '真实截图 OCR' } });
    fireEvent.click(screen.getByRole('button', { name: '整理粘贴文字' }));
    expect(await screen.findByText(/市值校验不通过/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '应用到持仓快照' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('航民股份price'), { target: { value: '6.69' } });
    fireEvent.change(screen.getByLabelText('航民股份market_value'), { target: { value: '669' } });
    expect(screen.queryByText(/市值校验不通过/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '应用到持仓快照' })).toBeEnabled();
  });
});
