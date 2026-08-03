import { useDashboardData } from '../hooks/useDashboardData';
import { useTradePlanPreview } from '../hooks/useTradePlan';
import { ThermometerWidget } from '../widgets/ThermometerWidget';
import { AllocationCardsWidget } from '../widgets/AllocationCardsWidget';
import { EquityRingWidget } from '../widgets/EquityRingWidget';
import { FactorRadarWidget } from '../widgets/FactorRadarWidget';
import { RiskBarWidget } from '../widgets/RiskBarWidget';
import { ValuationChartWidget } from '../widgets/ValuationChartWidget';
import { ActivityLogWidget } from '../widgets/ActivityLogWidget';
import { ProfitProtectionWidget } from '../widgets/ProfitProtectionWidget';
import GlassCard from '../components/GlassCard';
import { ExportPanel } from '../components/ExportPanel';
import { useState, useEffect, useMemo } from 'react';
import { ETF_TRACKING_INDEX } from '../types';
import type { HistoryResponse } from '../types';

// preview买单 reason_codes → 中文（与 ProfitProtectionWidget 的 REASON_LABELS 保持一致）
const REASON_LABELS_PREVIEW: Record<string, string> = {
  STRATEGIC_HARD_CAP: '突破战略硬上限',
  ANNUAL_SOFT_BAND: '12月年度软带',
  BOND_ANNUAL_SOFT_BAND: '国债多手年度再平衡',
  K50_HWM_DRAWDOWN_PARTIAL: '高水位回撤且趋势OFF',
  K50_TWO_MONTH_OFF_EXIT: '连续两个月趋势OFF',
  LOWER_BAND_REPAIR: '下限修复',
  TARGET_FILL: '目标补齐',
  HIGH_OPPORTUNITY_EXTENSION: '高机会扩展',
  BOND_POOL_EXECUTION: '国债累积池执行',
};

function useValuationHistory(asset: string, years: number) {
  const [history, setHistory] = useState<{ date: string; pePercentile: number | null; pbPercentile: number | null }[]>([]);
  useEffect(() => {
    let cancelled = false;
    const indexCode = ETF_TRACKING_INDEX[asset] ?? '000300';
    async function fetchBoth() {
      try {
        const [peRes, pbRes] = await Promise.all([
          fetch(`/api/history?index=${indexCode}&field=pe&years=${years}`),
          fetch(`/api/history?index=${indexCode}&field=pb&years=${years}`),
        ]);
        if (cancelled) return;
        if (!peRes.ok || !pbRes.ok) throw new Error(`History API ${peRes.status}/${pbRes.status}`);
        const peJson: HistoryResponse = await peRes.json();
        const pbJson: HistoryResponse = await pbRes.json();
        const peMap = new Map<string, number | null>(peJson.data.map(d => [d.date, d.percentile ?? null]));
        const pbMap = new Map<string, number | null>(pbJson.data.map(d => [d.date, d.percentile ?? null]));
        const allDates = [...new Set([...peMap.keys(), ...pbMap.keys()])].sort();
        setHistory(allDates.map(d => ({ date: d, pePercentile: peMap.get(d) ?? null, pbPercentile: pbMap.get(d) ?? null })));
      } catch {
        if (!cancelled) setHistory([]);
      }
    }
    fetchBoth();
    return () => { cancelled = true; };
  }, [asset, years]);
  return history;
}

export default function AiriDashboard() {
  const dash = useDashboardData();
  const tradePlan = useTradePlanPreview();
  const [selectedAsset, setSelectedAsset] = useState<string>('沪深300ETF');
  const [years, setYears] = useState(5);

  const valuationHistory = useValuationHistory(selectedAsset, years);

  // v1.3 退役后 GET report 只提供市场状态 + 因子分位，不再提供分配金额。
  // 金额的唯一数据源是 trade-plan preview 的 buys；无 preview 时不显示金额。
  const report = dash.report;

  // preview 买单 → 按资产名索引（金额来源）。无 preview 时为空 Map。
  const buyByAsset = useMemo(() => {
    const map = new Map<string, { amount: number; reason: string }>();
    const plan = tradePlan.data?.trade_plan;
    if (plan) {
      for (const b of plan.buys) {
        map.set(b.asset, {
          amount: Math.abs(b.cash_effect),
          reason: b.reason_codes.map(c => REASON_LABELS_PREVIEW[c] ?? c).join('、'),
        });
      }
    }
    return map;
  }, [tradePlan.data]);

  // 本月新增资金（仅在有 preview 时有意义；来自现金账本 new_money）。
  const newMoney = useMemo(() => {
    const plan = tradePlan.data?.trade_plan;
    if (!tradePlan.data?.snapshot_total_assets || !plan?.cash_ledger) return 0;
    return plan.cash_ledger.new_money ?? 0;
  }, [tradePlan.data]);

  // 从 report.assets 提取因子分；从 preview buys 提取金额。组合成卡片所需的视图。
  const { assets, scores } = useMemo(() => {
    const nextAssets: Record<string, { amount: number; triggerReason: string; opportunityScore: number | null; code?: string }> = {};
    const nextScores: Record<string, number | null> = {};
    for (const asset of report?.assets ?? []) {
      const buy = buyByAsset.get(asset.name);
      nextAssets[asset.name] = {
        amount: buy?.amount ?? 0,
        triggerReason: buy?.reason ?? asset.trigger_reason,
        opportunityScore: asset.score,
        code: asset.code,
      };
      nextScores[asset.name] = asset.score;
    }
    return { assets: nextAssets, scores: nextScores };
  }, [report, buyByAsset]);

  // ── 纯文本导出（微信/SMS 友好，无表格线） ──
  const exportText = useMemo(() => {
    if (!report) return '';
    const t = report.market_temp;
    const risk = report.portfolio_risk;
    const statusLabels: Record<string, string> = { cool: '估值合理 😊', mild_cool: '中等偏高 😐', strong_cool: '明显偏贵 😟', overheat: '极端过热 🥵', frozen: '温度冻结 ⏸️' };
    const pePct = t.hs300_pe_percentile != null ? Math.round(t.hs300_pe_percentile * 100) : null;
    const pbPct = t.all_a_pb_percentile != null ? Math.round(t.all_a_pb_percentile * 100) : null;
    const eqPct = Math.round(t.equity_ratio * 100);

    const fmtScore = (s: number | null) => {
      if (s == null) return '  —';
      const v = Math.round(s * 100);
      const icon = s >= 0.80 ? '🟢' : s >= 0.50 ? '🟡' : s >= 0.20 ? '🟠' : '🔴';
      return `${icon}${String(v).padStart(2)}`;
    };

    const pad = (s: string, w: number) => {
      // 中文字符约占2个英文字符宽度
      let len = 0; for (const c of s) len += /[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]/.test(c) ? 2 : 1;
      return s + ' '.repeat(Math.max(0, w - len));
    };

    const lines: string[] = [
      '📊  ETF-Allocator  本月配置',
      '━━━━━━━━━━━━━━━━━━━━━━━━━━',
      `🌡️ 市场  ${eqPct}%权益 · ${statusLabels[t.status] ?? t.status}`,
      pePct != null && pbPct != null
        ? `   PE ${pePct}%${pePct >= 90 ? '🔴' : pePct >= 80 ? '🟠' : pePct >= 60 ? '🟡' : '🟢'} · PB ${pbPct}%${pbPct >= 90 ? '🔴' : pbPct >= 80 ? '🟠' : pbPct >= 60 ? '🟡' : '🟢'}`
        : '',
      ...(t.status === 'frozen'
        ? [`   ⏸️ 冻结：PE(${pePct ?? '?'}%) vs PB(${pbPct ?? '?'}%) 信号不一致${eqPct === 70 ? ' → 维持默认70%' : ''}`]
        : []),
    ];

    // 新增资金（仅在有 preview 时显示）
    if (newMoney > 0) {
      lines.push('', `💰 新增资金  ¥${newMoney.toLocaleString()}`);
    }

    lines.push('');

    // 持仓占比（来自 GET report 的 weight_current，仅完整快照后非 0）
    const hasHoldings = report.assets.some(a => (a.weight_current ?? 0) > 0);
    if (hasHoldings) {
      lines.push('📋 当前持仓占比');
      for (const a of report.assets) {
        const wt = a.weight_current ?? 0;
        if (wt > 0) {
          const bar = '█'.repeat(Math.max(1, Math.round(wt * 20)));
          lines.push(`   ${pad(a.name.replace('ETF', ''), 6)} ${bar}  ${(wt * 100).toFixed(1)}%`);
        }
      }
      lines.push('');
    }

    // 资产机会分与（有 preview 时的）分配金额
    lines.push('📈 本月资产机会分' + (buyByAsset.size > 0 ? ' · 买单' : ''));
    for (const a of report.assets) {
      const name = a.name.replace('ETF', '');
      const score = a.score;
      const buy = buyByAsset.get(a.name);
      const amt = buy ? Math.round(buy.amount) : 0;
      const reason = buy?.reason ?? a.trigger_reason ?? (a.name === '国债ETF' ? '避险配置' : '');
      const excluded = score != null && score < 0.20 ? ' ⛔低分' : '';
      const amtStr = buyByAsset.size > 0
        ? (amt > 0 ? `¥${amt.toLocaleString()}` : '·')
        : '';
      lines.push(`   ${fmtScore(score)}  ${pad(name, 5)}  ${amtStr}${excluded}`);
      if (reason && reason.length < 30) lines.push(`           ${reason}`);
    }
    lines.push('');

    // 约束
    const vgWt2 = risk?.value_group_weight ?? 0; const vgCap2 = risk?.value_group_cap ?? 0.6;
    const ggWt2 = risk?.growth_group_weight ?? 0; const ggCap2 = risk?.growth_group_cap ?? 0.15;
    if (vgWt2 >= vgCap2 * 0.90 || ggWt2 >= ggCap2 * 0.90) {
      lines.push('⚠️  组合约束触达');
      if (vgWt2 >= vgCap2 * 0.90) lines.push(`   价值组 ${Math.round(vgWt2 * 100)}% / ${Math.round(vgCap2 * 100)}% 上限`);
      if (ggWt2 >= ggCap2 * 0.90) lines.push(`   成长组 ${Math.round(ggWt2 * 100)}% / ${Math.round(ggCap2 * 100)}% 上限`);
      lines.push('');
    }

    // 再平衡
    const rebDate = risk?.next_rebalance_date ?? '';
    if (rebDate) {
      lines.push(`📅 下次再平衡  ${rebDate}`);
      const deviation = eqPct - 50;
      if (Math.abs(deviation) > 5) {
        lines.push(`   权益偏离 ${deviation > 0 ? '+' : ''}${deviation}% （目标 50%）`);
      }
      lines.push('');
    }

    lines.push('━━━━━━━━━━━━━━━━━━━━━━━━━━');
    lines.push('via ETF-Allocator');
    return lines.join('\n');
  }, [report, buyByAsset, newMoney]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(exportText);
    } catch { /* ignore */ }
  };

  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: 'ETF-Allocator 本月配置', text: exportText });
      } catch { /* user cancelled */ }
    } else {
      handleCopy();
    }
  };

  // ... return JSX with share button

  return (
        <main className="px-4 sm:px-6 pb-8">
          <GlassCard title="盈利收获与交易计划" className="mb-4"
            info="完整快照模式读取份额、价格、平均成本和现金，输出正式卖单、科创50影子利润保护、纪律补仓买单与现金轧差。影子卖单只观察，不会自动执行。">
            <ProfitProtectionWidget tradePlan={tradePlan} />
          </GlassCard>

          {report ? (
            <div className="space-y-4">
              {dash.error && (
                <div className="bg-amber-50 border border-amber-200 rounded-2xl p-3 text-sm text-amber-800 mb-4" role="status">
                  数据刷新失败，当前显示上次成功结果。{dash.error}
                </div>
              )}
              {report.warnings && report.warnings.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-2xl p-3 text-sm text-amber-800 mb-4">
                  {report.warnings.map((w: string, i: number) => <div key={i}>⚠ {w}</div>)}
                </div>
              )}

              {/* Row 1: 温度计 | 权益仓位 | 活动日志 */}
              <div className="grid md:grid-cols-3 gap-4">
              <GlassCard title="市场温度计" info="双指标 AND 逻辑：沪深300 PE分位 + 全A PB分位。两者同区间→对应权益比(100/70/40/30%)；不同区间→冻结上期比例。首调用默认70%。">
                <ThermometerWidget {...dash.thermometerData} />
              </GlassCard>
              <GlassCard title="权益仓位" info="由市场温度计决定的可投权益比例。权益=可投股票ETF的资金占比；债=投国债ETF的资金占比。温度计降温时自动降低权益比例。但实际执行受组合约束限制（见下方导出面板）。">
                <EquityRingWidget {...dash.equityRingData} />
              </GlassCard>
                <GlassCard title="活动日志">
                  <ActivityLogWidget history={dash.activityLog} />
                </GlassCard>
              </div>

              {/* Row 2: 资产卡片（机会分来自 GET report，金额来自 preview buys，无 preview 时只显因子分） */}
              <GlassCard title={buyByAsset.size > 0 ? `本月补仓买单 (新增 ¥${newMoney.toLocaleString()})` : '本月资产机会分'}
                info="综合优先级 = 0.5×缺口分 + 0.5×机会分。缺口分衡量距目标下限差多少；机会分衡量当前估值吸引力(0-1)。<0.20自动排除。分配后检查因子组约束(VALUE≤60%, GROWTH≤15%)。

各资产机会分公式：
🍶 白酒    1 − PE分位
🏦 银行    σ(0.5·PB_z + 0.5·股息_z)
💰 红利    股息率分位
📊 沪深300 1 − PE分位
🔬 科创50  动量分位 × 趋势乘数
🏛 国债    不参与评分（吸收口）

未扫描完整快照时仅显示机会分（金额为 ¥0）；扫描后金额来自交易计划买单。">
                <AllocationCardsWidget assets={assets} onSelect={setSelectedAsset} selectedAsset={selectedAsset} hasPreview={buyByAsset.size > 0} />
              </GlassCard>

              {/* Row 3: 因子雷达 | 估值分位 */}
              <div className="grid md:grid-cols-5 gap-4">
                <GlassCard title="因子雷达" className="md:col-span-2"
                  info="各资产机会分(0-100)。白酒=1-PE分位；银行=sigmoid(PB_z+股息_z)；红利=股息率分位；沪深300=1-PE分位；科创50=动量分位×趋势开关。>80🟢 50-80🟡 20-50🟠 <20🔴。">
                  <FactorRadarWidget scores={scores} />
                </GlassCard>
                <GlassCard title="估值分位" className="md:col-span-3"
                  info="选中资产的PE/PB历史分位走势。分位=当前估值在过去N年中的百分位。高=贵(↓配置)，低=便宜(↑配置)。用expanding window(滚动起始点)防未来函数。">
                  <ValuationChartWidget history={valuationHistory} selectedAsset={selectedAsset} years={years} onYearsChange={setYears} />
                </GlassCard>
              </div>

              {/* Row 4: 组合风险 */}
              <GlassCard title="组合风险" info="因子组约束防伪分散：VALUE组(白酒+银行+红利)上限60%；沪深300独立为CORE，上限30%；GROWTH组(科创50)上限15%。完整快照模式下，无法成交的权益预算保留为权益待投现金。">
                <RiskBarWidget {...dash.riskData} />
              </GlassCard>

              {/* Row 5: 导出 / 分享 */}
              <GlassCard title="报告导出">
                <ExportPanel report={report} buyByAsset={buyByAsset} newMoney={newMoney} hasPreview={buyByAsset.size > 0} onCopy={handleCopy} onShare={handleShare} />
              </GlassCard>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-32 text-[var(--color-muted)]">
              {dash.loading ? (
                <>
                  <div className="w-10 h-10 rounded-full border-2 border-[var(--color-chromatic-300)] border-t-[var(--color-chromatic-600)] animate-spin mb-3" />
                  <span className="text-sm">加载配置数据...</span>
                </>
              ) : (
                <GlassCard className="text-center py-12">
                  <div className="text-[var(--color-dang)] text-lg font-medium mb-2">数据加载失败</div>
                  <div className="text-[var(--color-muted)] text-sm mb-4">{dash.error || '请确认后端服务已启动'}</div>
                  <button onClick={dash.refetch} className="px-4 py-2 rounded-xl text-sm font-medium text-white bg-[var(--color-chromatic-600)] hover:bg-[var(--color-chromatic-700)] transition cursor-pointer">重试</button>
                </GlassCard>
              )}
            </div>
          )}
        </main>
  );
}
