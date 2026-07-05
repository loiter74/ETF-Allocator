import { ThemeProvider } from '../contexts/ThemeContext';
import { useDashboardData } from '../hooks/useDashboardData';
import { useSimulate } from '../hooks/useReport';
import { ThermometerWidget } from '../widgets/ThermometerWidget';
import { AllocationCardsWidget } from '../widgets/AllocationCardsWidget';
import { EquityRingWidget } from '../widgets/EquityRingWidget';
import { FactorRadarWidget } from '../widgets/FactorRadarWidget';
import { RiskBarWidget } from '../widgets/RiskBarWidget';
import { ValuationChartWidget } from '../widgets/ValuationChartWidget';
import { ActivityLogWidget } from '../widgets/ActivityLogWidget';
import NavBar from '../components/NavBar';
import GlassCard from '../components/GlassCard';
import { ExportPanel } from '../components/ExportPanel';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { ETF_TRACKING_INDEX } from '../types';
import type { MonthlyReport } from '../types';

const DEFAULT_HOLDINGS = [
  { name: '白酒ETF', code: '161725', amount: 0 },
  { name: '银行ETF', code: '512800', amount: 0 },
  { name: '红利ETF', code: '515080', amount: 0 },
  { name: '沪深300ETF', code: '510300', amount: 0 },
  { name: '科创50ETF', code: '588000', amount: 0 },
  { name: '国债ETF', code: '511010', amount: 0 },
];

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
        const peJson = await peRes.json(); const pbJson = await pbRes.json();
        const peMap = new Map<string, number | null>((peJson.data ?? []).map((d: any) => [d.date, d.percentile ?? null]));
        const pbMap = new Map<string, number | null>((pbJson.data ?? []).map((d: any) => [d.date, d.percentile ?? null]));
        const allDates = [...new Set([...peMap.keys(), ...pbMap.keys()])].sort();
        setHistory(allDates.map(d => ({ date: d, pePercentile: peMap.get(d) ?? null, pbPercentile: pbMap.get(d) ?? null })));
      } catch { if (!cancelled) setHistory([]); }
    }
    fetchBoth();
    return () => { cancelled = true; };
  }, [asset, years]);
  return history;
}

/** 持仓输入行 */
function HoldingsInput({
  holdings, onChange,
}: {
  holdings: typeof DEFAULT_HOLDINGS;
  onChange: (index: number, amount: number) => void;
}) {
  const total = holdings.reduce((s, h) => s + h.amount, 0);
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
      {holdings.map((h, i) => (
        <div key={h.name} className="space-y-0.5">
          <label className="text-[11px] text-[#6B7280] block">
            {h.name.replace('ETF', '')}
            <span className="text-[#9CA3AF] ml-0.5">({h.code})</span>
          </label>
          <div className="relative">
            <span className="absolute left-2 top-1/2 -translate-y-1/2 text-[10px] text-[#9CA3AF]">¥</span>
            <input
              type="number"
              value={h.amount || ''}
              onChange={(e) => onChange(i, parseInt(e.target.value) || 0)}
              placeholder="0"
              className="w-full pl-5 pr-2 py-1.5 rounded-lg border border-gray-200 text-xs nums
                focus:outline-none focus:ring-1 focus:ring-[#7C3AED]/30 focus:border-[#7C3AED]
                bg-white/60 transition-all"
            />
          </div>
        </div>
      ))}
      <div className="flex items-end justify-between col-span-full pt-1 text-xs">
        <span className="text-[#9CA3AF]">持仓合计 <span className="nums font-medium text-[#1F2937]">¥{total.toLocaleString()}</span></span>
      </div>
    </div>
  );
}

export default function AiriDashboard() {
  const dash = useDashboardData();
  const { data: simData, loading: simLoading, simulate } = useSimulate();
  const [selectedAsset, setSelectedAsset] = useState<string>('沪深300ETF');
  const [years, setYears] = useState(5);

  // 持仓持久化：从 localStorage 恢复
  const [holdings, setHoldings] = useState<typeof DEFAULT_HOLDINGS>(() => {
    try {
      const saved = localStorage.getItem('etf-allocator-holdings');
      if (saved) return JSON.parse(saved);
    } catch {}
    return DEFAULT_HOLDINGS;
  });
  const [newMoney, setNewMoney] = useState<number>(() => {
    try {
      const saved = localStorage.getItem('etf-allocator-new-money');
      if (saved) return parseInt(saved, 10) || 8000;
    } catch {}
    return 8000;
  });
  const valuationHistory = useValuationHistory(selectedAsset, years);

  const totalAssets = holdings.reduce((s, h) => s + h.amount, 0);

  // 用模拟结果覆盖 dashboard 数据
  const report: MonthlyReport | null = simData
    ? {
        date: simData.date,
        market_temp: dash.report?.market_temp ?? { equity_ratio: 0.7, bond_ratio: 0.3, status: 'cool',
          hs300_pe_percentile: 0, all_a_pb_percentile: 0, hs300_pe_percentile_long: null, all_a_pb_percentile_long: null },
        portfolio_risk: dash.report?.portfolio_risk ?? { value_group_weight: 0, value_group_cap: 0.6, growth_group_weight: 0, growth_group_cap: 0.15, next_rebalance_date: '' },
        allocations: simData.allocations.map((a: any) => ({
          ...a,
          trigger_reason: a.trigger_reason ?? '',
          current_weight: a.current_weight ?? 0,
          upper_limit: a.upper_limit ?? 0.3,
        })),
        new_money: newMoney,
      }
    : dash.report;

  const handleHoldingsChange = useCallback((index: number, value: number) => {
    setHoldings(prev => prev.map((h, i) => (i === index ? { ...h, amount: Math.max(0, value) } : h)));
  }, []);

  const handleCalculate = () => {
    if (totalAssets <= 0) {
      setHoldings(prev => prev.map(h => ({ ...h, amount: 0 })));
      return;
    }
    const weights: Record<string, number> = {};
    holdings.forEach(h => { weights[h.name] = h.amount / totalAssets; });
    const today = new Date();
    const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    simulate({ date: dateStr, new_money: newMoney, total_assets: totalAssets, current_weights: weights });
    // 持久化到 localStorage
    try {
      localStorage.setItem('etf-allocator-holdings', JSON.stringify(holdings));
      localStorage.setItem('etf-allocator-new-money', String(newMoney));
    } catch {}
  };

  // 从 report 提取 scores 和 allocations 数据
  const allocs: Record<string, { amount: number; triggerReason: string; opportunityScore: number | null; code?: string }> = {};
  const scores: Record<string, number | null> = {};
  if (report?.allocations) {
    for (const a of report.allocations) {
      allocs[a.asset] = { amount: a.amount, triggerReason: a.trigger_reason, opportunityScore: a.opportunity_score, code: (a as any).code };
      scores[a.asset] = a.opportunity_score;
    }
  }

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
      `   ⏸️ 冻结：PE(${pePct ?? '?'}%) vs PB(${pbPct ?? '?'}%) 信号不一致` +
        (eqPct === 70 ? ' → 维持默认70%' : ''),
      '',
      `💰 新增资金  ¥${(report.new_money ?? 0).toLocaleString()}`,
    ];

    // 权益缺口：温度计建议 vs 约束后实际
    const targetEq = (report.new_money ?? 0) * t.equity_ratio;
    const actualEq = report.allocations
      .filter((a: any) => a.asset !== '国债ETF')
      .reduce((s: number, a: any) => s + Math.round(a.amount), 0);
    const eqGap = Math.round(targetEq - actualEq);
    if (eqGap > 10) {
      lines.push(`   🌡️ 温度计建议  ¥${Math.round(targetEq).toLocaleString()}`);
      lines.push(`   ⚠️ 约束后实际  ¥${actualEq.toLocaleString()}`);
      lines.push(`   ➡ 差额 ¥${eqGap.toLocaleString()} 转入国债（组合已满）`);
    }
    lines.push('');

    // 持仓占比
    const curWt2: Record<string, number> = {};
    for (const a of report.allocations) curWt2[a.asset] = (a as any).current_weight ?? 0;
    const hasHoldings = Object.values(curWt2).some(v => v > 0);
    if (hasHoldings) {
      lines.push('📋 分配前持仓');
      for (const a of report.allocations) {
        const wt = curWt2[a.asset] ?? 0;
        if (wt > 0) {
          const bar = '█'.repeat(Math.max(1, Math.round(wt * 20)));
          lines.push(`   ${pad(a.asset.replace('ETF', ''), 6)} ${bar}  ${(wt * 100).toFixed(1)}%`);
        }
      }
      lines.push('');
    }

    // 分配建议
    lines.push('📈 本月分配建议');
    for (const a of report.allocations) {
      const name = a.asset.replace('ETF', '');
      const amt = Math.round(a.amount);
      const score = a.opportunity_score;
      const reason = a.trigger_reason || (a.asset === '国债ETF' ? '避险配置' : '');
      const excluded = amt === 0 && score != null && score < 0.20 ? ' ⛔已排除' : '';
      const amtStr = amt > 0 ? `¥${amt.toLocaleString()}` : '·';
      lines.push(`   ${fmtScore(score)}  ${pad(name, 5)}  ${amtStr}${excluded}`);
      if (reason && reason.length < 30) lines.push(`           ${reason}`);
    }
    lines.push('');

    // 国债累积池状态
    const bs = report.bond_status;
    if (bs) {
      if (bs.action_buy) {
        lines.push(`🏛️ 国债  本月买入 ¥${Math.round(bs.action_amount).toLocaleString()}（${bs.action_lots}手）`);
        lines.push(`   池余额 ¥${Math.round(bs.balance).toLocaleString()} · 累计利息 ¥${bs.total_interest.toFixed(1)}`);
      } else {
        const pct = Math.round(bs.balance / bs.min_purchase * 100);
        const remaining = bs.min_purchase - bs.balance;
        const mLeft = bs.deposit_this_month > 0 ? Math.ceil(remaining / bs.deposit_this_month) : null;
        lines.push(`🏛️ 国债  累积中 ¥${Math.round(bs.balance).toLocaleString()} / ¥${Math.round(bs.min_purchase).toLocaleString()}（${pct}%）`);
        lines.push(`   本月存入 ¥${Math.round(bs.deposit_this_month).toLocaleString()} · 利息 ¥${bs.total_interest.toFixed(1)}`);
        if (mLeft != null) lines.push(`   预计 ${mLeft} 个月后可购买`);
      }
      lines.push('');
    }

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
  }, [report]);

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
    <ThemeProvider>
      <div className="min-h-screen font-sans bg-[#FFFBF0]">
        <NavBar />
        <main className="px-4 sm:px-6 pb-8">
          {/* ── 持仓设置（可折叠） ── */}
          <details className="mb-4 group" open={false}>
            <summary className="text-sm font-medium text-[#7C3AED] cursor-pointer px-3 py-2 rounded-xl bg-[#7C3AED]/5 hover:bg-[#7C3AED]/10 transition-colors select-none">
              ⚙ 持仓设置
            </summary>
            <div className="mt-3 p-4 rounded-2xl bg-white/60 border border-gray-100 space-y-3">
              <HoldingsInput holdings={holdings} onChange={handleHoldingsChange} />
              <div className="flex items-center gap-3 pt-2 border-t border-gray-100">
                <div className="flex items-center gap-2">
                  <label className="text-xs text-[#6B7280]">新增资金</label>
                  <div className="relative">
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 text-[10px] text-[#9CA3AF]">¥</span>
                    <input type="number" value={newMoney} onChange={e => setNewMoney(Math.max(0, parseInt(e.target.value) || 0))}
                      className="w-28 pl-5 pr-2 py-1.5 rounded-lg border border-gray-200 text-xs nums focus:outline-none focus:ring-1 focus:ring-[#7C3AED]/30 bg-white/60" />
                  </div>
                </div>
                <button onClick={handleCalculate} disabled={simLoading || totalAssets <= 0}
                  className="px-5 py-1.5 rounded-lg text-xs font-semibold text-white bg-gradient-to-r from-[#7C3AED] to-[#EC4899]
                    hover:shadow-md disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer">
                  {simLoading ? '计算中...' : '计算分配'}
                </button>
                {simData && <span className="text-xs text-[#10B981] font-medium">✓ 已用自定义持仓计算</span>}
              </div>
            </div>
          </details>

          {report ? (
            <div className="space-y-4">
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

              {/* Row 2: 分配卡片 */}
              <GlassCard title={`本月新增资金分配 (¥${(report.new_money ?? newMoney).toLocaleString()})`}
                info="综合优先级 = 0.5×缺口分 + 0.5×机会分。缺口分衡量距目标下限差多少；机会分衡量当前估值吸引力(0-1)。<0.20自动排除。分配后检查因子组约束(VALUE≤60%, GROWTH≤15%)。
                
各资产机会分公式：
🍶 白酒    1 − PE分位
🏦 银行    σ(0.5·PB_z + 0.5·股息_z)
💰 红利    股息率分位
📊 沪深300 1 − PE分位  
🔬 科创50  动量分位 × 趋势乘数
🏛 国债    不参与评分（吸收口）">
                <AllocationCardsWidget allocations={allocs} onSelect={setSelectedAsset} selectedAsset={selectedAsset} bondStatus={dash.bondStatus} />
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
              <GlassCard title="组合风险" info="因子组约束防伪分散：VALUE组(白酒+银行+红利+沪深300)上限60%；GROWTH组(科创50)上限15%。超限时组内等比缩减，溢出进国债。">
                <RiskBarWidget {...dash.riskData} />
              </GlassCard>

              {/* Row 5: 导出 / 分享 */}
              <GlassCard title="报告导出">
                <ExportPanel report={report} onCopy={handleCopy} onShare={handleShare} />
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
      </div>
    </ThemeProvider>
  );
}
