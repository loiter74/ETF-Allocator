import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import InvestmentHistory from '../pages/InvestmentHistory';
import type { MonthlyReport } from '../types';
import { AllocationCardsWidget } from '../widgets/AllocationCardsWidget';
import { ExportPanel } from './ExportPanel';

afterEach(() => {
  vi.restoreAllMocks();
  window.history.pushState({}, '', '/');
});

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function makeReport(status: string, growthWeight = 0.1): MonthlyReport {
  return {
    date: '2026-07-12',
    market_temp: {
      hs300_pe_percentile: 0.72,
      all_a_pb_percentile: 0.68,
      equity_ratio: 0.7,
      bond_ratio: 0.3,
      status,
    },
    portfolio_risk: {
      value_group_weight: 0.2,
      value_group_cap: 0.6,
      growth_group_weight: growthWeight,
      growth_group_cap: 0.15,
      next_rebalance_date: '',
    },
    assets: [{
      name: '国债ETF',
      code: '511010',
      factor_group: 'BOND',
      score: null,
      weight_current: 0.3,
      weight_upper: 1,
      weight_lower: 0.1,
      trigger_reason: '国债避险配置',
    }],
  };
}

describe('frontend bug regressions', () => {
  it('does not label a normal thermometer result as frozen', () => {
    const { rerender } = render(<ExportPanel report={makeReport('mild_cool')} buyByAsset={new Map()} newMoney={0} hasPreview={false} onCopy={vi.fn()} onShare={vi.fn()} />);
    expect(screen.queryByText(/温度计冻结/)).not.toBeInTheDocument();

    rerender(<ExportPanel report={makeReport('frozen')} buyByAsset={new Map()} newMoney={0} hasPreview={false} onCopy={vi.fn()} onShare={vi.fn()} />);
    expect(screen.getByText(/温度计冻结/)).toBeInTheDocument();
  });

  it('shows a growth limit warning even when the value group is below its limit', () => {
    render(<ExportPanel report={makeReport('mild_cool', 0.14)} buyByAsset={new Map()} newMoney={0} hasPreview={false} onCopy={vi.fn()} onShare={vi.fn()} />);
    expect(screen.getByText(/成长组上限/)).toBeInTheDocument();
    expect(screen.queryByText(/价值组上限/)).not.toBeInTheDocument();
  });

  it('renders a bond asset card showing the preview buy amount', () => {
    render(<AllocationCardsWidget assets={{
      国债ETF: {
        amount: 2400,
        triggerReason: '国债避险配置',
        opportunityScore: null,
        code: '511010',
      },
    }} hasPreview />);
    expect(screen.getByText('¥2,400')).toBeInTheDocument();
  });

  it('redirects the removed simulator route to the dashboard', async () => {
    window.history.pushState({}, '', '/simulator');
    render(<App />);
    await waitFor(() => expect(window.location.pathname).toBe('/'));
    expect(screen.getByText('本月概览')).toBeInTheDocument();
    expect(screen.getByText('资金记录')).toBeInTheDocument();
    expect(screen.queryByText('持仓模拟')).not.toBeInTheDocument();
  });

  it('creates a confirmed investment and refreshes the summary', async () => {
    const emptyPayload = {
      records: [],
      summary: { count: 0, total_amount: 0, last_date: null, last_amount: null },
    };
    const populatedPayload = {
      records: [{
        id: 1,
        investment_date: '2026-07-12',
        amount: 8000,
        allocations: {
          白酒ETF: 3000,
          银行ETF: 0,
          红利ETF: 0,
          沪深300ETF: 0,
          科创50ETF: 0,
          国债ETF: 5000,
        },
        note: '七月投入',
        created_at: '2026-07-12T01:00:00Z',
      }],
      summary: { count: 1, total_amount: 8000, last_date: '2026-07-12', last_amount: 8000 },
    };
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(emptyPayload))
      .mockResolvedValueOnce(jsonResponse(populatedPayload.records[0], 201))
      .mockResolvedValueOnce(jsonResponse(populatedPayload));

    render(<InvestmentHistory />);
    expect(await screen.findByText('还没有投入记录')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('白酒投入金额'), { target: { value: '3000' } });
    fireEvent.change(screen.getByLabelText('国债投入金额'), { target: { value: '5000' } });
    fireEvent.change(screen.getByLabelText(/备注/), { target: { value: '七月投入' } });
    fireEvent.click(screen.getByRole('button', { name: '确认已投入 ¥8,000' }));

    await waitFor(() => expect(screen.getAllByText('¥8,000').length).toBeGreaterThanOrEqual(2));
    expect(screen.getByText('七月投入')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/investments', expect.objectContaining({ method: 'POST' }));
    const postOptions = fetchMock.mock.calls[1][1] as RequestInit;
    expect(JSON.parse(postOptions.body as string)).toMatchObject({
      allocations: { 白酒ETF: 3000, 国债ETF: 5000 },
      note: '七月投入',
    });
  });
});
