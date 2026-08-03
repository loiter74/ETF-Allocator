import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SnapshotImportResponse, TradePlanPreviewResponse } from '../types';
import { ProfitProtectionWidget } from './ProfitProtectionWidget';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function previewResponse(): TradePlanPreviewResponse {
  const exposure = {
    total_assets: 2624,
    managed_total: 2624,
    managed_weights: { 科创50ETF: 0.2378 },
    group_weights: { GROWTH: 0.2378 },
    account_equity_ratio: 0.2378,
    defense_ratio: 0,
    unknown_value: 0,
  };
  return {
    snapshot_total_assets: 2624,
    read_only: true,
    protection_status: {
      mode: 'shadow',
      active: true,
      cycle_id: 1,
      high_watermark: 1.18,
      off_months: 1,
      on_months: 0,
      pending_trigger: 'K50_HWM_DRAWDOWN_PARTIAL',
      profit_return: 0.30,
      drawdown_from_high: 0.1186,
      activated_this_month: false,
      trend_on: false,
      opportunity_score: 0.42,
      triggered: true,
      trigger_reason_codes: ['K50_HWM_DRAWDOWN_PARTIAL'],
      thresholds: {
        activation_return: 0.25,
        drawdown_trigger: 0.12,
        off_months_exit: 2,
        partial_sell_fraction: 1 / 3,
      },
    },
    trade_plan: {
      plan_id: 'profit-preview-1',
      snapshot_date: '2026-08-02',
      phase: 'complete',
      formal_sells: [],
      shadow_sells: [{
        side: 'SELL',
        asset: '科创50ETF',
        code: '588000',
        reason_codes: ['K50_HWM_DRAWDOWN_PARTIAL'],
        shares: 200,
        reference_price: 1.04,
        estimated_price: 1.03948,
        gross_amount: 207.90,
        commission: 5,
        slippage_cost: 0.10,
        cash_effect: 202.90,
        mandatory: true,
        shadow: true,
        allocation_stages: [],
      }],
      buys: [],
      warnings: [],
      before: exposure,
      after: exposure,
      cash_ledger: {
        opening_cash: 2000,
        new_money: 8000,
        sell_net_proceeds: 0,
        buy_cash_outflow: 0,
        closing_cash: 10000,
        bond_pool_before: 0,
        bond_pool_deposit: 0,
        bond_pool_released: 0,
        bond_pool_after: 0,
        equity_pending_before: 0,
        equity_pending_after: 10000,
        free_cash_after: 0,
        total_commission: 0,
        total_slippage: 0,
        cash_identity_error: 0,
      },
      pending_buy_recalculation: false,
      legacy_allocation_only: false,
    },
  };
}

function snapshotImportResponse(): SnapshotImportResponse {
  const numberField = (value: number | null) => ({ value, confidence: value == null ? 0 : 0.92, source: value == null ? 'missing' : 'local_parser', evidence: '识别行', value_date: null });
  const stringField = (value: string | null) => ({ value, confidence: value == null ? 0 : 0.92, source: value == null ? 'missing' : 'local_parser', evidence: '识别行', value_date: null });
  return {
    provider: 'local_parser', model: null, warnings: [], input_characters: 50, read_only: true, image_uploaded: false,
    draft: {
      snapshot_date: stringField('2026-08-02'),
      account_cash: numberField(2272),
      positions: [{
        asset: stringField('科创50ETF'), code: stringField('588000'),
        shares: numberField(600), price: numberField(1.04), average_cost: numberField(0.8), market_value: numberField(624),
        is_equity: true, warnings: [],
      }],
    },
  };
}

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('ProfitProtectionWidget', () => {
  it('submits a complete position snapshot and renders the shadow profit order', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse(previewResponse()));
    render(<ProfitProtectionWidget />);

    fireEvent.change(screen.getByLabelText('科创50ETF份额'), { target: { value: '600' } });
    fireEvent.change(screen.getByLabelText('科创50ETF当前价格'), { target: { value: '1.04' } });
    fireEvent.change(screen.getByLabelText('科创50ETF平均成本'), { target: { value: '0.80' } });
    fireEvent.change(screen.getByLabelText('账户现金'), { target: { value: '2000' } });
    fireEvent.click(screen.getByRole('button', { name: '扫描盈利与交易计划' }));

    expect(await screen.findByTestId('trade-plan-result')).toBeInTheDocument();
    expect(screen.getByText('30.0%')).toBeInTheDocument();
    expect(screen.getByText(/已命中利润保护条件/)).toBeInTheDocument();
    expect(screen.getByText('模拟卖出 科创50ETF')).toBeInTheDocument();
    expect(screen.getByText(/200 份/)).toBeInTheDocument();
    expect(screen.getByText(/高水位回撤且趋势OFF/)).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith('/api/trade-plan/preview', expect.objectContaining({ method: 'POST' }));
    const previewCall = fetchMock.mock.calls.find(call => call[0] === '/api/trade-plan/preview');
    const options = previewCall?.[1] as RequestInit;
    const body = JSON.parse(options.body as string);
    expect(body.snapshot.positions).toContainEqual(expect.objectContaining({
      asset: '科创50ETF',
      shares: 600,
      price: 1.04,
      average_cost: 0.8,
      market_value: 624,
    }));
    expect(body.snapshot.account_cash).toBe(2000);
  });

  it('blocks a snapshot with shares but no current price before calling the API', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    render(<ProfitProtectionWidget />);

    fireEvent.change(screen.getByLabelText('科创50ETF份额'), { target: { value: '600' } });
    fireEvent.click(screen.getByRole('button', { name: '扫描盈利与交易计划' }));

    expect(screen.getByRole('alert')).toHaveTextContent('科创50ETF已有份额，请填写当前价格');
    await waitFor(() => expect(fetchMock).not.toHaveBeenCalledWith(
      '/api/trade-plan/preview', expect.anything(),
    ));
  });

  it('keeps shadow mode visibly distinct from an executable sell', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse(previewResponse()));
    render(<ProfitProtectionWidget />);

    fireEvent.click(screen.getByRole('button', { name: '扫描盈利与交易计划' }));

    expect(await screen.findByText('影子模式')).toBeInTheDocument();
    expect(screen.getByText('科创影子止盈单')).toBeInTheDocument();
    expect(screen.getByText('正式卖单')).toBeInTheDocument();
    expect(screen.getByText('本月没有战略硬上限或年度软带卖单。')).toBeInTheDocument();
  });

  it('applies a reviewed OCR draft to the form without automatically scanning trades', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async input => {
      const url = String(input);
      if (url.includes('parse-text')) return jsonResponse(snapshotImportResponse());
      if (url.includes('ocr-config')) return jsonResponse({ image_upload: false, ocr_location: 'browser' });
      return jsonResponse({}, 500);
    });
    render(<ProfitProtectionWidget />);

    fireEvent.change(screen.getByLabelText('OCR文字'), { target: { value: '科创50ETF 持仓份额600 现价1.04 成本0.8' } });
    fireEvent.click(screen.getByRole('button', { name: '整理粘贴文字' }));
    expect(await screen.findByTestId('snapshot-import-review')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '应用到持仓快照' }));

    expect(screen.getByLabelText('科创50ETF份额')).toHaveValue(600);
    expect(screen.getByLabelText('科创50ETF当前价格')).toHaveValue(1.04);
    expect(screen.getByLabelText('科创50ETF平均成本')).toHaveValue(0.8);
    expect(screen.getByLabelText('账户现金')).toHaveValue(2272);
    expect(fetchMock.mock.calls.some(call => String(call[0]).includes('trade-plan'))).toBe(false);
  });
});
