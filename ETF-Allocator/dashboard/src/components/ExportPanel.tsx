
import type { MonthlyReport } from '../types';

interface BuyInfo {
  amount: number;
  reason: string;
}

interface Props {
  report: MonthlyReport;
  /** preview 买单按资产名索引（金额来源）；无 preview 时为空 Map。 */
  buyByAsset: Map<string, BuyInfo>;
  /** 本月新增资金（来自 preview 现金账本）。无 preview 时为 0。 */
  newMoney: number;
  /** 是否存在 preview；false 时隐藏金额列与新增资金卡片。 */
  hasPreview: boolean;
  onCopy: () => void;
  onShare: () => void;
}

const scoreColor = (s: number | null): string => {
  if (s == null) return '#9CA3AF';
  if (s >= 0.80) return '#10B981';
  if (s >= 0.50) return '#F59E0B';
  if (s >= 0.20) return '#F97316';
  return '#EF4444';
};

export function ExportPanel({ report, buyByAsset, newMoney, hasPreview, onCopy, onShare }: Props) {
  if (!report) return null;
  const t = report.market_temp;
  const risk = report.portfolio_risk;
  const statusLabels: Record<string, string> = { cool: '估值合理', mild_cool: '中等偏高', strong_cool: '明显偏贵', overheat: '极端过热', frozen: '温度冻结' };
  const pePct = t.hs300_pe_percentile != null ? Math.round(t.hs300_pe_percentile * 100) : null;
  const pbPct = t.all_a_pb_percentile != null ? Math.round(t.all_a_pb_percentile * 100) : null;
  const eqPct = Math.round(t.equity_ratio * 100);
  const rebDate = risk?.next_rebalance_date ?? '';
  const deviation = eqPct - 50;

  return (
    <div className="space-y-3 text-sm">
      {/* Header + Market */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="col-span-2 sm:col-span-4 flex items-center gap-2 text-base font-bold text-[#1F2937]">
          📊 ETF-Allocator 本月配置
        </div>
        <div className="bg-purple-50 rounded-xl p-3 text-center">
          <div className="text-[10px] text-[#6B7280] mb-1">市场温度</div>
          <div className="text-lg font-bold text-[#7C3AED]">{eqPct}%</div>
          <div className="text-[10px] text-[#6B7280]">{statusLabels[t.status] ?? t.status}</div>
        </div>
        <div className="bg-amber-50 rounded-xl p-3 text-center">
          <div className="text-[10px] text-[#6B7280] mb-1">沪深300 PE</div>
          <div className={`text-lg font-bold ${(pePct ?? 0) >= 90 ? 'text-[#EF4444]' : (pePct ?? 0) >= 80 ? 'text-[#F97316]' : 'text-[#10B981]'}`}>
            {pePct ?? '—'}%
          </div>
        </div>
        <div className="bg-green-50 rounded-xl p-3 text-center">
          <div className="text-[10px] text-[#6B7280] mb-1">全A PB</div>
          <div className={`text-lg font-bold ${(pbPct ?? 0) >= 90 ? 'text-[#EF4444]' : 'text-[#10B981]'}`}>
            {pbPct ?? '—'}%
          </div>
        </div>
        <div className="bg-blue-50 rounded-xl p-3 text-center">
          <div className="text-[10px] text-[#6B7280] mb-1">新增资金</div>
          <div className="text-lg font-bold text-[#2563EB]">
            {hasPreview ? `¥${newMoney.toLocaleString()}` : '—'}
          </div>
        </div>
      </div>

      {/* Thermometer Reason */}
      {t.status === 'frozen' && pePct != null && pbPct != null && (
        <div className="bg-gray-50 rounded-xl p-3 flex items-center gap-2 text-xs text-[#6B7280]">
          <span>⏸️</span>
          <span>温度计冻结 · PE <span className="font-bold text-[#1F2937]">{pePct}%</span>
            vs PB <span className="font-bold text-[#1F2937]">{pbPct}%</span>
            ，信号档位不一致，维持 {eqPct}% 权益</span>
        </div>
      )}

      {/* Holdings */}
      <div className="bg-white rounded-xl border border-gray-100 p-3">
        <div className="text-xs font-medium text-[#6B7280] mb-2">当前持仓占比</div>
        <div className="space-y-1.5">
          {report.assets.map(a => {
            const name = a.name.replace('ETF', '');
            const wt = a.weight_current ?? 0;
            const hasData = wt > 0;
            return (
              <div key={a.name} className="flex items-center gap-2">
                <span className="w-12 text-xs text-[#374151] shrink-0">{name}</span>
                <div className="flex-1 h-4 bg-gray-100 rounded-full overflow-hidden">
                  {hasData ? (
                    <div className="h-full bg-[#7C3AED]/30 rounded-full flex items-center justify-end pr-2" style={{ width: `${Math.min(wt * 100, 100)}%` }}>
                      <span className="text-[10px] text-[#7C3AED] font-medium nums">{(wt * 100).toFixed(1)}%</span>
                    </div>
                  ) : null}
                </div>
                {!hasData && <span className="text-[10px] text-[#D1D5DB] w-10 text-right">—</span>}
              </div>
            );
          })}
        </div>
      </div>

      {/* Allocation */}
      <div className="bg-white rounded-xl border border-gray-100 p-3">
        <div className="text-xs font-medium text-[#6B7280] mb-2">{hasPreview ? '本月补仓买单' : '本月资产机会分'}</div>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-100 text-[#9CA3AF]">
              <th className="text-left py-1.5 w-6">#</th>
              <th className="text-left py-1.5">资产</th>
              <th className="text-center py-1.5 w-10">分</th>
              {hasPreview && <th className="text-right py-1.5 w-20">金额</th>}
              <th className="text-left py-1.5 hidden sm:table-cell">因子</th>
            </tr>
          </thead>
          <tbody>
            {report.assets.map((a, i) => {
              const name = a.name.replace('ETF', '');
              const score = a.score;
              const sc = score != null ? Math.round(score * 100) : null;
              const buy = buyByAsset.get(a.name);
              const amt = buy ? Math.round(buy.amount) : 0;
              const excluded = score != null && score < 0.20;
              return (
                <tr key={a.name} className={`border-b border-gray-50 ${excluded ? 'opacity-50' : ''} ${hasPreview && amt > 0 ? 'bg-purple-50/30' : ''}`}>
                  <td className="py-2 text-[#9CA3AF]">{i + 1}</td>
                  <td className="py-2 font-medium text-[#1F2937]">
                    {name}
                    <span className="text-[#9CA3AF] ml-1 text-[10px]">{a.code}</span>
                  </td>
                  <td className="py-2 text-center">
                    {sc != null ? (
                      <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold" style={{ background: scoreColor(score) + '20', color: scoreColor(score) }}>
                        {sc}
                      </span>
                    ) : (
                      <span className="text-[#D1D5DB]">—</span>
                    )}
                  </td>
                  {hasPreview && (
                    <td className={`py-2 text-right nums font-semibold ${amt > 0 ? 'text-[#1F2937]' : 'text-[#D1D5DB]'}`}>
                      {amt > 0 ? `¥${amt.toLocaleString()}` : '—'}
                    </td>
                  )}
                  <td className="py-2 text-[#6B7280] hidden sm:table-cell text-xs">
                    {buy?.reason ?? a.trigger_reason ?? (a.name === '国债ETF' ? '避险配置' : '')}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Constraints */}
      {((risk?.value_group_weight ?? 0) >= (risk?.value_group_cap ?? 0.6) * 0.90 ||
        (risk?.growth_group_weight ?? 0) >= (risk?.growth_group_cap ?? 0.15) * 0.90) && (
        <div className="grid grid-cols-2 gap-2 text-xs">
          {(risk?.value_group_weight ?? 0) >= (risk?.value_group_cap ?? 0.6) * 0.90 && (
            <div className="bg-amber-50 rounded-xl p-3">
              <span className="text-amber-700">⚠️ 价值组上限</span>
              <span className="text-amber-600 nums ml-1">{Math.round((risk?.value_group_weight ?? 0) * 100)}% / {Math.round((risk?.value_group_cap ?? 0.6) * 100)}%</span>
            </div>
          )}
          {(risk?.growth_group_weight ?? 0) >= (risk?.growth_group_cap ?? 0.15) * 0.90 && (
            <div className="bg-amber-50 rounded-xl p-3">
              <span className="text-amber-700">⚠️ 成长组上限</span>
              <span className="text-amber-600 nums ml-1">{Math.round((risk?.growth_group_weight ?? 0) * 100)}% / {Math.round((risk?.growth_group_cap ?? 0.15) * 100)}%</span>
            </div>
          )}
        </div>
      )}

      {/* Rebalance */}
      {rebDate && (
        <div className="bg-blue-50 rounded-xl p-3 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span>📅</span>
            <span className="text-[#374151]">下次再平衡 <span className="font-medium">{rebDate}</span></span>
          </div>
          {Math.abs(deviation) > 5 && (
            <span className="nums font-medium text-[#2563EB]">
              权益偏离 {deviation > 0 ? '+' : ''}{deviation}%（目标50%）
            </span>
          )}
        </div>
      )}

      {/* Buttons */}
      <div className="flex gap-2">
        <button onClick={onCopy}
          className="flex-1 py-2 rounded-xl text-xs font-medium bg-white border border-gray-200 text-[#374151] hover:bg-gray-50 transition cursor-pointer">
          📋 复制文本
        </button>
        <button onClick={onShare}
          className="flex-1 py-2 rounded-xl text-xs font-medium text-white bg-gradient-to-r from-[#7C3AED] to-[#EC4899] hover:shadow-md transition cursor-pointer">
          📤 分享
        </button>
      </div>
    </div>
  );
}
