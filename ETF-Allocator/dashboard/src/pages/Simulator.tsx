import { useState, useCallback } from 'react'
import { useSimulate } from '../hooks/useReport'
import GlassCard from '../components/GlassCard'
import { SkeletonCard } from '../components/Skeleton'
import type { SimulateResponse } from '../types'

interface Holding {
  name: string
  code: string
  amount: number
}

const DEFAULT_HOLDINGS: Holding[] = [
  { name: '白酒ETF', code: '161725', amount: 24000 },
  { name: '银行ETF', code: '512800', amount: 44000 },
  { name: '红利ETF', code: '515080', amount: 30000 },
  { name: '沪深300ETF', code: '510300', amount: 36000 },
  { name: '科创50ETF', code: '588000', amount: 20000 },
  { name: '国债ETF', code: '511010', amount: 46000 },
]

function formatAmount(amount: number): string {
  return `¥${amount.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

export default function Simulator() {
  const [holdings, setHoldings] = useState<Holding[]>(DEFAULT_HOLDINGS)
  const [newMoney, setNewMoney] = useState(10000)
  const { data, loading, error, simulate } = useSimulate()

  const totalAssets = holdings.reduce((sum, h) => sum + h.amount, 0)

  const handleAmount = useCallback(
    (index: number, value: number) => {
      setHoldings((prev) =>
        prev.map((h, i) => (i === index ? { ...h, amount: Math.max(0, value) } : h))
      )
    },
    []
  )

  const handleCalculate = () => {
    const weights: Record<string, number> = {}
    if (totalAssets > 0) {
      holdings.forEach((h) => {
        weights[h.name] = h.amount / totalAssets
      })
    }
    const today = new Date()
    const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
    simulate({ date: dateStr, new_money: newMoney, total_assets: totalAssets, current_weights: weights })
  }

  return (
    <div className="px-4 sm:px-6 pb-6 sm:pb-8">
      <div className="grid md:grid-cols-2 grid-cols-1 gap-4 sm:gap-6">
        {/* Left: Input Panel */}
        <GlassCard title="持仓设置">
          <div className="space-y-3">
            {holdings.map((holding, i) => (
              <div key={holding.name}>
                <label className="text-sm text-[#1F2937] font-medium">
                  {holding.name.replace('ETF', '')}
                  <span className="text-[#9CA3AF] ml-1 text-xs">({holding.code})</span>
                </label>
                <div className="relative mt-1">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#6B7280] text-sm">¥</span>
                  <input
                    type="number"
                    value={holding.amount || ''}
                    onChange={(e) => handleAmount(i, parseInt(e.target.value) || 0)}
                    placeholder="0"
                    className="w-full pl-8 pr-3 py-2 rounded-xl border border-gray-200 text-sm nums
                      focus:outline-none focus:ring-2 focus:ring-[#7C3AED]/20 focus:border-[#7C3AED]
                      bg-white/60 transition-all"
                  />
                </div>
              </div>
            ))}

            <div className="border-t border-gray-100 pt-3 flex justify-between text-sm">
              <span className="text-[#6B7280]">持仓合计</span>
              <span className="nums font-semibold text-[#1F2937]">{formatAmount(totalAssets)}</span>
            </div>

            <div>
              <label className="text-sm text-[#6B7280] block mb-1">本月新增资金</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#6B7280] text-sm">¥</span>
                <input
                  type="number"
                  value={newMoney}
                  onChange={(e) => setNewMoney(Math.max(0, parseInt(e.target.value) || 0))}
                  className="w-full pl-8 pr-3 py-2 rounded-xl border border-gray-200 text-sm nums
                    focus:outline-none focus:ring-2 focus:ring-[#7C3AED]/20 focus:border-[#7C3AED]
                    bg-white/60 transition-all"
                />
              </div>
            </div>

            <button
              onClick={handleCalculate}
              disabled={loading}
              className="w-full py-2.5 rounded-xl text-sm font-semibold text-white
                bg-gradient-to-r from-[#7C3AED] to-[#EC4899]
                hover:shadow-lg hover:shadow-purple-200
                disabled:opacity-40 disabled:cursor-not-allowed
                transition-all duration-200 active:scale-[0.98]"
            >
              {loading ? '计算中...' : '计算分配'}
            </button>
          </div>
        </GlassCard>

        {/* Right: Results Panel */}
        <div>
          {loading ? (
            <SkeletonCard className="h-full" />
          ) : error ? (
            <GlassCard className="text-center py-12">
              <div className="text-[#EF4444] text-sm mb-1">请求失败</div>
              <div className="text-[#6B7280] text-xs">{error}</div>
            </GlassCard>
          ) : data ? (
            <ResultsPanel data={data} />
          ) : (
            <GlassCard className="text-center py-16 h-full flex flex-col items-center justify-center">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#7C3AED" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="mb-3 opacity-40">
                <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
              <p className="text-[#6B7280] text-sm">输入持仓金额后点击"计算分配"</p>
            </GlassCard>
          )}
        </div>
      </div>
    </div>
  )
}

function ResultsPanel({ data }: { data: SimulateResponse & { allocations: any[] } }) {
  return (
    <div className="space-y-4">
      <GlassCard title="本月分配">
        <div className="space-y-2">
          {data.allocations.map((item: any) => (
            <div
              key={item.asset}
              className={`flex items-center justify-between py-2 px-3 rounded-xl transition-all ${
                item.amount > 0 ? 'bg-purple-50' : 'bg-white/50 opacity-60'
              }`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-sm font-medium text-[#1F2937] truncate">{item.asset.replace('ETF', '')}</span>
                {item.opportunity_score != null && (
                  <span
                    className="nums text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0"
                    style={{
                      backgroundColor:
                        item.opportunity_score >= 0.7
                          ? 'rgba(16, 185, 129, 0.1)'
                          : item.opportunity_score >= 0.4
                            ? 'rgba(245, 158, 11, 0.1)'
                            : 'rgba(239, 68, 68, 0.1)',
                      color:
                        item.opportunity_score >= 0.7
                          ? '#10B981'
                          : item.opportunity_score >= 0.4
                            ? '#F59E0B'
                            : '#EF4444',
                    }}
                  >
                    {Math.round(item.opportunity_score * 100)}分
                  </span>
                )}
                {item.trigger_reason && (
                  <span className="text-[10px] text-[#9CA3AF] truncate hidden sm:inline">{item.trigger_reason}</span>
                )}
              </div>
              <span className={`nums text-sm font-semibold shrink-0 ml-2 ${item.amount > 0 ? 'text-[#1F2937]' : 'text-[#D1D5DB]'}`}>
                {formatAmount(item.amount)}
              </span>
            </div>
          ))}
        </div>
      </GlassCard>

      <GlassCard title="权重对比">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="text-left py-2 pr-2 text-[#6B7280] font-medium text-xs">资产</th>
              <th className="text-right py-2 px-2 text-[#6B7280] font-medium text-xs nums">调整前</th>
              <th className="text-right py-2 px-2 text-[#6B7280] font-medium text-xs nums">调整后</th>
              <th className="text-right py-2 pl-2 text-[#6B7280] font-medium text-xs nums">变动</th>
            </tr>
          </thead>
          <tbody>
            {data.allocations.map((item: any) => {
              const before = (data.before_weights[item.asset] ?? 0) * 100
              const after = (data.after_weights[item.asset] ?? 0) * 100
              const diff = after - before
              return (
                <tr key={item.asset} className="border-b border-gray-50">
                  <td className="py-2 pr-2 text-[#1F2937] text-xs">{item.asset.replace('ETF', '')}</td>
                  <td className="py-2 px-2 text-right nums text-[#6B7280] text-xs">{before.toFixed(1)}%</td>
                  <td className="py-2 px-2 text-right nums font-medium text-[#1F2937] text-xs">{after.toFixed(1)}%</td>
                  <td
                    className={`py-2 pl-2 text-right nums font-medium text-xs ${
                      Math.abs(diff) < 0.01 ? 'text-[#6B7280]' : diff > 0 ? 'text-[#10B981]' : 'text-[#EF4444]'
                    }`}
                  >
                    {Math.abs(diff) < 0.01 ? '—' : `${diff > 0 ? '+' : ''}${diff.toFixed(1)}%`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </GlassCard>
    </div>
  )
}
