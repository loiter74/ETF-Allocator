import { useMemo, useState } from 'react';
import { BrokerScreenshotImport } from '../components/BrokerScreenshotImport';
import { useTradePlanPreview } from '../hooks/useTradePlan';
import { formatLocalDate } from '../lib/utils';
import type {
  PortfolioPositionInput,
  ProfitProtectionStatus,
  SnapshotImportDraft,
  TradeOrder,
  TradePlanPreviewRequest,
} from '../types';

const SNAPSHOT_STORAGE_KEY = 'etf-allocator-portfolio-snapshot-v2';

const MANAGED_ASSETS = [
  { asset: '白酒ETF', code: '161725', isEquity: true },
  { asset: '银行ETF', code: '512800', isEquity: true },
  { asset: '红利ETF', code: '515080', isEquity: true },
  { asset: '沪深300ETF', code: '510300', isEquity: true },
  { asset: '科创50ETF', code: '588000', isEquity: true },
  { asset: '国债ETF', code: '511010', isEquity: false },
] as const;

interface PositionDraft {
  asset: string;
  code: string;
  isEquity: boolean;
  shares: number;
  price: number;
  averageCost: number;
}

interface SnapshotDraft {
  snapshotDate: string;
  priceDate: string;
  newMoney: number;
  accountCash: number;
  bondPoolCash: number;
  reverseRepoCash: number;
  equityPendingCash: number;
  otherEquityValue: number;
  positions: PositionDraft[];
}

const NUMBER_INPUT_CLASS = `w-full min-w-24 rounded-lg border border-[var(--color-border)] bg-white/70
  px-2 py-1.5 text-xs tabular-nums text-[#1F2937] outline-none transition
  focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent-light)]`;

const REASON_LABELS: Record<string, string> = {
  STRATEGIC_HARD_CAP: '突破战略硬上限',
  ANNUAL_SOFT_BAND: '12月年度软带再平衡',
  BOND_ANNUAL_SOFT_BAND: '国债多手年度再平衡',
  K50_HWM_DRAWDOWN_PARTIAL: '高水位回撤且趋势OFF',
  K50_TWO_MONTH_OFF_EXIT: '连续两个月趋势OFF',
  LOWER_BAND_REPAIR: '下限修复',
  TARGET_FILL: '目标补齐',
  HIGH_OPPORTUNITY_EXTENSION: '高机会扩展',
  BOND_POOL_EXECUTION: '国债累积池达到门槛',
};

function emptyDraft(): SnapshotDraft {
  const today = formatLocalDate();
  return {
    snapshotDate: today,
    priceDate: today,
    newMoney: 8000,
    accountCash: 0,
    bondPoolCash: 0,
    reverseRepoCash: 0,
    equityPendingCash: 0,
    otherEquityValue: 0,
    positions: MANAGED_ASSETS.map(item => ({
      ...item,
      shares: 0,
      price: 0,
      averageCost: 0,
    })),
  };
}

function nonNegative(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : fallback;
}

function loadDraft(): SnapshotDraft {
  const fallback = emptyDraft();
  try {
    const raw = localStorage.getItem(SNAPSHOT_STORAGE_KEY);
    if (!raw) {
      const savedNewMoney = localStorage.getItem('etf-allocator-new-money');
      return { ...fallback, newMoney: nonNegative(savedNewMoney, fallback.newMoney) };
    }
    const saved = JSON.parse(raw) as Partial<SnapshotDraft>;
    const savedPositions = Array.isArray(saved.positions) ? saved.positions : [];
    return {
      ...fallback,
      snapshotDate: typeof saved.snapshotDate === 'string' ? saved.snapshotDate : fallback.snapshotDate,
      priceDate: typeof saved.priceDate === 'string' ? saved.priceDate : fallback.priceDate,
      newMoney: nonNegative(saved.newMoney, fallback.newMoney),
      accountCash: nonNegative(saved.accountCash),
      bondPoolCash: nonNegative(saved.bondPoolCash),
      reverseRepoCash: nonNegative(saved.reverseRepoCash),
      equityPendingCash: nonNegative(saved.equityPendingCash),
      otherEquityValue: nonNegative(saved.otherEquityValue),
      positions: fallback.positions.map(position => {
        const savedPosition = savedPositions.find(item => item?.asset === position.asset);
        return {
          ...position,
          shares: nonNegative(savedPosition?.shares),
          price: nonNegative(savedPosition?.price),
          averageCost: nonNegative(savedPosition?.averageCost),
        };
      }),
    };
  } catch {
    return fallback;
  }
}

function money(value: number): string {
  return `¥${Math.round(value).toLocaleString('zh-CN')}`;
}

function percent(value: number | null, digits = 1): string {
  return value == null ? '—' : `${(value * 100).toFixed(digits)}%`;
}

function protectionMessage(status: ProfitProtectionStatus, hasPosition: boolean): string {
  const activation = status.thresholds.activation_return;
  if (!hasPosition) return '当前快照未持有科创50，利润保护不触发。';
  if (status.profit_return == null) return '缺少科创50平均成本，无法判断浮盈和激活保护。';
  if (status.triggered) return '本月已命中利润保护条件；影子单只模拟，不会自动卖出。';
  if (status.activated_this_month) return '浮盈达到激活线且趋势ON，本月新激活保护周期。';
  if (status.active) {
    return status.trend_on
      ? '保护周期运行中，月末价格继续更新高水位。'
      : '保护周期运行中，正在等待回撤或连续OFF条件确认。';
  }
  if (status.profit_return >= activation && !status.trend_on) {
    return '浮盈已达激活线，但趋势OFF；规则不会在弱趋势中开启新周期。';
  }
  const gap = Math.max(0, activation - status.profit_return);
  return `尚未达到激活线，还差 ${percent(gap)}。`;
}

function OrderList({ title, orders, emptyText, shadow = false }: {
  title: string;
  orders: TradeOrder[];
  emptyText: string;
  shadow?: boolean;
}) {
  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-white/55 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-[#1F2937]">{title}</h4>
        <span className="rounded-full bg-[var(--color-surface-2)] px-2 py-0.5 text-[10px] text-[var(--color-muted)]">
          {orders.length} 笔
        </span>
      </div>
      {orders.length === 0 ? (
        <p className="text-xs leading-5 text-[var(--color-muted)]">{emptyText}</p>
      ) : (
        <div className="space-y-2">
          {orders.map(order => (
            <div key={`${order.side}-${order.asset}-${order.reason_codes.join('-')}`} className="rounded-lg bg-[var(--color-surface-1)] p-2.5 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-[#1F2937]">
                  {shadow ? '模拟卖出' : order.side === 'SELL' ? '卖出' : '买入'} {order.asset}
                </span>
                <span className="tabular-nums font-semibold text-[var(--color-accent)]">
                  {order.shares.toLocaleString('zh-CN')} 份 · {money(Math.abs(order.cash_effect))}
                </span>
              </div>
              <div className="mt-1 text-[11px] leading-5 text-[var(--color-muted)]">
                预计价 ¥{order.estimated_price.toFixed(4)} · 佣金 {money(order.commission)}
                {' · '}{order.reason_codes.map(code => REASON_LABELS[code] ?? code).join('、')}
              </div>
              {order.side === 'BUY' && order.stage_breakdown && Object.keys(order.stage_breakdown).length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px] leading-4 text-[var(--color-muted)]">
                  <span className="opacity-70">阶段明细：</span>
                  {Object.entries(order.stage_breakdown)
                    .sort((a, b) => b[1] - a[1])
                    .map(([stage, amount]) => (
                      <span key={stage} className="rounded bg-[var(--color-surface-2)] px-1.5 py-0.5">
                        {REASON_LABELS[stage] ?? stage} {money(amount)}
                      </span>
                    ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function ProfitProtectionWidget({ tradePlan }: {
  tradePlan: ReturnType<typeof useTradePlanPreview>;
}) {
  const [draft, setDraft] = useState<SnapshotDraft>(loadDraft);
  const [validationError, setValidationError] = useState<string | null>(null);
  const { data, loading, error, preview, reset } = tradePlan;

  const positionsValue = useMemo(
    () => draft.positions.reduce((sum, position) => sum + position.shares * position.price, 0),
    [draft.positions],
  );
  const totalAssets = positionsValue + draft.accountCash + draft.reverseRepoCash + draft.otherEquityValue;
  const k50Draft = draft.positions.find(position => position.asset === '科创50ETF');

  const setCashField = (field: keyof Omit<SnapshotDraft, 'positions' | 'snapshotDate' | 'priceDate'>, value: number) => {
    setDraft(current => ({ ...current, [field]: Math.max(0, value) }));
  };

  const setPosition = (index: number, field: 'shares' | 'price' | 'averageCost', value: number) => {
    setDraft(current => ({
      ...current,
      positions: current.positions.map((position, positionIndex) => (
        positionIndex === index ? { ...position, [field]: Math.max(0, value) } : position
      )),
    }));
  };

  const applyImportedDraft = (imported: SnapshotImportDraft) => {
    const importedByAsset = new Map(
      imported.positions
        .filter(position => typeof position.asset.value === 'string')
        .map(position => [position.asset.value as string, position]),
    );
    const otherEquityValue = imported.positions.reduce((sum, position) => {
      const asset = position.asset.value;
      if (!position.is_equity || (typeof asset === 'string' && MANAGED_ASSETS.some(item => item.asset === asset))) return sum;
      const marketValue = Number(position.market_value.value ?? 0);
      const derived = Number(position.shares.value ?? 0) * Number(position.price.value ?? 0);
      return sum + Math.max(0, marketValue || derived);
    }, 0);
    setDraft(current => ({
      ...current,
      snapshotDate: typeof imported.snapshot_date.value === 'string' ? imported.snapshot_date.value : current.snapshotDate,
      priceDate: typeof imported.snapshot_date.value === 'string' ? imported.snapshot_date.value : current.priceDate,
      accountCash: typeof imported.account_cash.value === 'number' ? imported.account_cash.value : current.accountCash,
      otherEquityValue: otherEquityValue > 0 ? otherEquityValue : current.otherEquityValue,
      positions: current.positions.map(position => {
        const recognized = importedByAsset.get(position.asset);
        if (!recognized) return position;
        return {
          ...position,
          shares: typeof recognized.shares.value === 'number' ? recognized.shares.value : position.shares,
          price: typeof recognized.price.value === 'number' ? recognized.price.value : position.price,
          averageCost: typeof recognized.average_cost.value === 'number' ? recognized.average_cost.value : position.averageCost,
        };
      }),
    }));
    setValidationError(null);
    reset();
  };

  const handlePreview = () => {
    const invalidPosition = draft.positions.find(position => position.shares > 0 && position.price <= 0);
    if (invalidPosition) {
      setValidationError(`${invalidPosition.asset}已有份额，请填写当前价格。`);
      return;
    }
    if (draft.bondPoolCash + draft.equityPendingCash > draft.accountCash + 0.01) {
      setValidationError('国债累积池与权益待投现金不能超过账户现金。');
      return;
    }
    if (!draft.snapshotDate || !draft.priceDate || draft.priceDate > draft.snapshotDate) {
      setValidationError('请填写有效日期，且价格日期不能晚于快照日期。');
      return;
    }

    const positions: PortfolioPositionInput[] = draft.positions
      .filter(position => position.shares > 0)
      .map(position => ({
        asset: position.asset,
        code: position.code,
        shares: position.shares,
        price: position.price,
        market_value: position.shares * position.price,
        average_cost: position.averageCost > 0 ? position.averageCost : null,
        is_equity: position.isEquity,
      }));
    if (draft.otherEquityValue > 0) {
      positions.push({
        asset: '其他权益',
        code: 'OTHER',
        shares: draft.otherEquityValue,
        price: 1,
        market_value: draft.otherEquityValue,
        average_cost: null,
        is_equity: true,
      });
    }

    const request: TradePlanPreviewRequest = {
      snapshot: {
        snapshot_date: draft.snapshotDate,
        price_date: draft.priceDate,
        new_money: draft.newMoney,
        account_cash: draft.accountCash,
        bond_pool_cash: draft.bondPoolCash,
        reverse_repo_cash: draft.reverseRepoCash,
        equity_pending_cash: draft.equityPendingCash,
        positions,
      },
    };
    setValidationError(null);
    try {
      localStorage.setItem(SNAPSHOT_STORAGE_KEY, JSON.stringify(draft));
    } catch {
      // A valid preview must not depend on browser storage availability.
    }
    void preview(request);
  };

  const plan = data?.trade_plan;
  const protection = data?.protection_status;
  const hasK50Position = Boolean(k50Draft && k50Draft.shares > 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-xl border border-[var(--color-accent-light)] bg-[var(--color-chromatic-50)] p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-[#1F2937]">科创50盈利收获</span>
            <span className="rounded-full bg-[var(--color-warn)]/15 px-2 py-0.5 text-[10px] font-semibold text-[var(--color-warn)]">
              影子观察 · 不自动卖出
            </span>
          </div>
          <p className="mt-1 text-xs leading-5 text-[var(--color-muted)]">
            完整快照必须包含份额、现价和券商平均成本；系统按月检查 +25% 激活、12%高水位回撤和连续趋势OFF。
          </p>
        </div>
        <div className="text-left sm:text-right">
          <div className="text-[11px] text-[var(--color-muted)]">快照总资产</div>
          <div className="tabular-nums text-lg font-semibold text-[#1F2937]">{money(totalAssets)}</div>
        </div>
      </div>

      <details className="group rounded-xl border border-[var(--color-border)] bg-white/45" open>
        <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-[var(--color-accent)]">
          录入完整月度快照
        </summary>
        <div className="space-y-4 border-t border-[var(--color-border)] p-4">
          <BrokerScreenshotImport snapshotDate={draft.snapshotDate} onApply={applyImportedDraft} />

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <label className="space-y-1 text-[11px] text-[var(--color-muted)]">
              <span>快照日期</span>
              <input aria-label="快照日期" type="date" value={draft.snapshotDate}
                onChange={event => setDraft(current => ({ ...current, snapshotDate: event.target.value }))}
                className={NUMBER_INPUT_CLASS} />
            </label>
            <label className="space-y-1 text-[11px] text-[var(--color-muted)]">
              <span>价格日期</span>
              <input aria-label="价格日期" type="date" value={draft.priceDate}
                onChange={event => setDraft(current => ({ ...current, priceDate: event.target.value }))}
                className={NUMBER_INPUT_CLASS} />
            </label>
            <label className="space-y-1 text-[11px] text-[var(--color-muted)]">
              <span>本月新增资金</span>
              <input aria-label="本月新增资金" type="number" min="0" step="0.01" value={draft.newMoney || ''}
                onChange={event => setCashField('newMoney', nonNegative(event.target.value))}
                className={NUMBER_INPUT_CLASS} />
            </label>
            <label className="space-y-1 text-[11px] text-[var(--color-muted)]">
              <span>账户现金</span>
              <input aria-label="账户现金" type="number" min="0" step="0.01" value={draft.accountCash || ''}
                onChange={event => setCashField('accountCash', nonNegative(event.target.value))}
                className={NUMBER_INPUT_CLASS} />
            </label>
            <label className="space-y-1 text-[11px] text-[var(--color-muted)]">
              <span>国债累积池（现金标记）</span>
              <input aria-label="国债累积池" type="number" min="0" step="0.01" value={draft.bondPoolCash || ''}
                onChange={event => setCashField('bondPoolCash', nonNegative(event.target.value))}
                className={NUMBER_INPUT_CLASS} />
            </label>
            <label className="space-y-1 text-[11px] text-[var(--color-muted)]">
              <span>权益待投现金</span>
              <input aria-label="权益待投现金" type="number" min="0" step="0.01" value={draft.equityPendingCash || ''}
                onChange={event => setCashField('equityPendingCash', nonNegative(event.target.value))}
                className={NUMBER_INPUT_CLASS} />
            </label>
            <label className="space-y-1 text-[11px] text-[var(--color-muted)]">
              <span>逆回购</span>
              <input aria-label="逆回购" type="number" min="0" step="0.01" value={draft.reverseRepoCash || ''}
                onChange={event => setCashField('reverseRepoCash', nonNegative(event.target.value))}
                className={NUMBER_INPUT_CLASS} />
            </label>
            <label className="space-y-1 text-[11px] text-[var(--color-muted)]">
              <span>其他权益市值（仅计风险）</span>
              <input aria-label="其他权益市值" type="number" min="0" step="0.01" value={draft.otherEquityValue || ''}
                onChange={event => setCashField('otherEquityValue', nonNegative(event.target.value))}
                className={NUMBER_INPUT_CLASS} />
            </label>
          </div>

          <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
            <table className="w-full min-w-[700px] text-left text-xs">
              <thead className="bg-[var(--color-surface-2)] text-[11px] text-[var(--color-muted)]">
                <tr>
                  <th className="px-3 py-2 font-medium">资产</th>
                  <th className="px-3 py-2 font-medium">份额</th>
                  <th className="px-3 py-2 font-medium">当前价格</th>
                  <th className="px-3 py-2 font-medium">平均成本</th>
                  <th className="px-3 py-2 text-right font-medium">市值</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {draft.positions.map((position, index) => (
                  <tr key={position.asset} className={position.asset === '科创50ETF' ? 'bg-[var(--color-chromatic-50)]/70' : 'bg-white/45'}>
                    <td className="px-3 py-2 font-medium text-[#1F2937]">
                      {position.asset}<span className="ml-1 text-[10px] font-normal text-[var(--color-muted)]">{position.code}</span>
                    </td>
                    <td className="px-3 py-2">
                      <input aria-label={`${position.asset}份额`} type="number" min="0" step="1" value={position.shares || ''}
                        onChange={event => setPosition(index, 'shares', nonNegative(event.target.value))}
                        className={NUMBER_INPUT_CLASS} />
                    </td>
                    <td className="px-3 py-2">
                      <input aria-label={`${position.asset}当前价格`} type="number" min="0" step="0.0001" value={position.price || ''}
                        onChange={event => setPosition(index, 'price', nonNegative(event.target.value))}
                        className={NUMBER_INPUT_CLASS} />
                    </td>
                    <td className="px-3 py-2">
                      <input aria-label={`${position.asset}平均成本`} type="number" min="0" step="0.0001" value={position.averageCost || ''}
                        onChange={event => setPosition(index, 'averageCost', nonNegative(event.target.value))}
                        placeholder={position.asset === '科创50ETF' ? '盈利保护必填' : '可选'}
                        className={NUMBER_INPUT_CLASS} />
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-[#1F2937]">
                      {money(position.shares * position.price)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {(validationError || error) && (
            <div role="alert" className="rounded-lg border border-[var(--color-dang)]/30 bg-[var(--color-dang)]/10 px-3 py-2 text-xs text-[var(--color-dang)]">
              {validationError || error}
            </div>
          )}
          {hasK50Position && (!k50Draft?.averageCost || k50Draft.averageCost <= 0) && (
            <div className="rounded-lg border border-[var(--color-warn)]/30 bg-[var(--color-warn)]/10 px-3 py-2 text-xs text-[var(--color-warn)]">
              科创50已有持仓但未填写平均成本：可以买入扫描，但无法判断盈利保护。
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[11px] leading-5 text-[var(--color-muted)]">
              预览不会写入策略状态；高水位只在后续显式确认月度观察时保存。
            </p>
            <button type="button" onClick={handlePreview} disabled={loading}
              className="rounded-xl bg-[var(--color-accent)] px-5 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50">
              {loading ? '扫描中…' : '扫描盈利与交易计划'}
            </button>
          </div>
        </div>
      </details>

      {!data && !loading && !error && (
        <div className="rounded-xl border border-dashed border-[var(--color-border)] p-5 text-center text-xs leading-6 text-[var(--color-muted)]">
          填写快照后扫描。这里会明确显示“为什么不卖”、正式卖单、科创影子止盈单和补仓买单。
        </div>
      )}

      {protection && plan && (
        <div className="space-y-4" data-testid="trade-plan-result">
          <section role="status" className="rounded-xl border border-[var(--color-accent-light)] bg-white/60 p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-base font-semibold text-[#1F2937]">科创50利润保护状态</h4>
                  <span className="rounded-full bg-[var(--color-warn)]/15 px-2 py-0.5 text-[10px] font-semibold text-[var(--color-warn)]">
                    {protection.mode === 'shadow' ? '影子模式' : '正式模式'}
                  </span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${protection.trend_on
                    ? 'bg-[var(--color-safe)]/15 text-[var(--color-safe)]'
                    : 'bg-[var(--color-dang)]/10 text-[var(--color-dang)]'}`}>
                    趋势 {protection.trend_on ? 'ON' : 'OFF'}
                  </span>
                </div>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-[#374151]">
                  {protectionMessage(protection, hasK50Position)}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div className="rounded-lg bg-[var(--color-surface-1)] px-3 py-2 text-center">
                  <div className="text-[10px] text-[var(--color-muted)]">当前浮盈</div>
                  <div className={`mt-1 tabular-nums text-base font-semibold ${(protection.profit_return ?? 0) >= 0
                    ? 'text-[var(--color-positive)]'
                    : 'text-[var(--color-negative)]'}`}>
                    {percent(protection.profit_return)}
                  </div>
                </div>
                <div className="rounded-lg bg-[var(--color-surface-1)] px-3 py-2 text-center">
                  <div className="text-[10px] text-[var(--color-muted)]">保护高水位</div>
                  <div className="mt-1 tabular-nums text-base font-semibold text-[#1F2937]">
                    {protection.high_watermark > 0 ? `¥${protection.high_watermark.toFixed(4)}` : '—'}
                  </div>
                </div>
                <div className="rounded-lg bg-[var(--color-surface-1)] px-3 py-2 text-center">
                  <div className="text-[10px] text-[var(--color-muted)]">高位回撤</div>
                  <div className="mt-1 tabular-nums text-base font-semibold text-[#1F2937]">
                    {percent(protection.drawdown_from_high)}
                  </div>
                </div>
                <div className="rounded-lg bg-[var(--color-surface-1)] px-3 py-2 text-center">
                  <div className="text-[10px] text-[var(--color-muted)]">连续 OFF</div>
                  <div className="mt-1 tabular-nums text-base font-semibold text-[#1F2937]">
                    {protection.off_months} 月
                  </div>
                </div>
              </div>
            </div>
            <div className="mt-3 rounded-lg bg-[var(--color-surface-2)] px-3 py-2 text-[11px] leading-5 text-[var(--color-muted)]">
              锁定规则：浮盈 {percent(protection.thresholds.activation_return, 0)} 且趋势ON激活；从高水位回撤
              {' '}{percent(protection.thresholds.drawdown_trigger, 0)} 且趋势OFF模拟卖出
              {' '}{percent(protection.thresholds.partial_sell_fraction, 0)}；连续 {protection.thresholds.off_months_exit} 个月OFF优先模拟降至5%。
            </div>
          </section>

          <div className="grid gap-3 lg:grid-cols-3">
            <OrderList title="正式卖单" orders={plan.formal_sells} emptyText="本月没有战略硬上限或年度软带卖单。" />
            <OrderList title="科创影子止盈单" orders={plan.shadow_sells} emptyText="本月未同时满足已激活、回撤/连续OFF条件。" shadow />
            <OrderList title="纪律补仓买单" orders={plan.buys} emptyText={plan.pending_buy_recalculation ? '等待真实卖出成交后重算。' : '本月没有满足条件且可执行的买单。'} />
          </div>

          <section className="grid gap-3 rounded-xl border border-[var(--color-border)] bg-white/55 p-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <div className="text-[10px] text-[var(--color-muted)]">全账户权益</div>
              <div className="mt-1 tabular-nums text-sm font-semibold text-[#1F2937]">{percent(plan.before.account_equity_ratio)}</div>
            </div>
            <div>
              <div className="text-[10px] text-[var(--color-muted)]">防御桶</div>
              <div className="mt-1 tabular-nums text-sm font-semibold text-[#1F2937]">{percent(plan.before.defense_ratio)}</div>
            </div>
            <div>
              <div className="text-[10px] text-[var(--color-muted)]">期末现金</div>
              <div className="mt-1 tabular-nums text-sm font-semibold text-[#1F2937]">{plan.cash_ledger ? money(plan.cash_ledger.closing_cash) : '—'}</div>
            </div>
            <div>
              <div className="text-[10px] text-[var(--color-muted)]">预估交易成本</div>
              <div className="mt-1 tabular-nums text-sm font-semibold text-[#1F2937]">
                {plan.cash_ledger ? money(plan.cash_ledger.total_commission + plan.cash_ledger.total_slippage) : '—'}
              </div>
            </div>
          </section>

          {plan.warnings.length > 0 && (
            <section className="rounded-xl border border-[var(--color-warn)]/30 bg-[var(--color-warn)]/10 p-3 text-xs leading-5 text-[#6B5724]">
              {plan.warnings.map(warning => <div key={warning}>⚠ {warning}</div>)}
            </section>
          )}
        </div>
      )}
    </div>
  );
}
