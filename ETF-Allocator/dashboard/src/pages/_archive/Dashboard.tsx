import { useState } from 'react'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid, ReferenceLine,
} from 'recharts'
import { useReport, useSimulate } from '../hooks/useReport'
import { useHistory } from '../hooks/useHistory'
import GlassCard from '../components/GlassCard'
import ProgressBar from '../components/ProgressBar'
import { SkeletonCard, SkeletonTable } from '../components/Skeleton'
import type { SimulateResponse, HistoryPoint } from '../types'

const INDEX_KEYS = ['沪深300', '中证白酒', '中证银行', '中证红利', '科创50'] as const
type IndexKey = typeof INDEX_KEYS[number]

const PIE_COLORS: Record<string, string> = {
  VALUE: '#7C3AED',
  GROWTH: '#EC4899',
  DEFENSE: '#10B981',
}

function statusBg(status: string): string {
  const s = status.toLowerCase()
  if (s.includes('过热') || s.includes('高估') || s.includes('危险')) return 'bg-red-50 text-red-600'
  if (s.includes('正常') || s.includes('适中')) return 'bg-emerald-50 text-emerald-600'
  if (s.includes('低估')) return 'bg-purple-50 text-purple-600'
  return 'bg-amber-50 text-amber-600'
}

function fmt(amount: number): string {
  return `¥${amount.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function scoreColor(s: number | null): string {
  if (s === null) return '#6B7280'
  if (s >= 0.7) return '#10B981'
  if (s >= 0.4) return '#F59E0B'
  return '#EF4444'
}

// ── Pie tooltip ──
function PieTooltip({ active, payload }: { active?: boolean; payload?: Array<{ name: string; value: number }> }) {
  if (!active || !payload?.length) return null
  return (
    <div className="glass-card px-3 py-2 text-xs shadow-md">
      <div className="font-medium text-[#1F2937]">{payload[0].name}</div>
      <div className="nums text-[#7C3AED]">{fmt(payload[0].value)}</div>
    </div>
  )
}

// ── Line tooltip ──
function LineTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number }>; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="glass-card px-3 py-2 text-xs shadow-md">
      <div className="text-[#6B7280] mb-1">{label}</div>
      <div className="nums font-semibold text-[#1F2937]">{payload[0].value.toFixed(1)}%</div>
    </div>
  )
}

function formatTickDate(dateStr: string): string {
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

// ── Simulate Section ──
interface AssetWeight { name: string; weight: number }

const DEFAULT_ASSETS: AssetWeight[] = [
  { name: '白酒ETF', weight: 12 },
  { name: '银行ETF', weight: 22 },
  { name: '红利ETF', weight: 15 },
  { name: '沪深300ETF', weight: 18 },
  { name: '科创50ETF', weight: 10 },
  { name: '国债ETF', weight: 23 },
]

function normalizeWeights(weights: AssetWeight[], idx: number, val: number): AssetWeight[] {
  const clamped = Math.max(0, Math.min(val, 100))
  const n = weights.length
  const otherSum = weights.reduce((s, w, i) => (i !== idx ? s + w.weight : s), 0)
  const remaining = 100 - clamped
  const result = weights.map((w, i) => {
    if (i === idx) return { ...w, weight: clamped }
    if (otherSum === 0) return { ...w, weight: remaining / (n - 1) }
    return { ...w, weight: (w.weight / otherSum) * remaining }
  })
  const sum = result.reduce((s, w) => s + w.weight, 0)
  const diff = Math.round((100 - sum) * 100) / 100
  if (Math.abs(diff) > 0.001) {
    const others = result.map((w, i) => ({ ...w, idx: i })).filter((_, i) => i !== idx)
    const maxIdx = others.reduce((a, b) => (a.weight > b.weight ? a : b)).idx
    result[maxIdx] = { ...result[maxIdx], weight: Math.round((result[maxIdx].weight + diff) * 100) / 100 }
  }
  return result.map((w) => ({ ...w, weight: Math.round(w.weight * 100) / 100 }))
}

function SimulateSection() {
  const [assets, setAssets] = useState<AssetWeight[]>(DEFAULT_ASSETS)
  const [totalAssets, setTotalAssets] = useState(200000)
  const [newMoney, setNewMoney] = useState(10000)
  const { data, loading, error, simulate } = useSimulate()

  const handleCalculate = () => {
    const weights: Record<string, number> = {}
    assets.forEach((a) => { weights[a.name] = a.weight / 100 })
    const today = new Date()
    const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
    simulate({ date: dateStr, new_money: newMoney, total_assets: totalAssets, current_weights: weights })
  }

  return (
    <GlassCard title="模拟器">
      <div className="grid md:grid-cols-2 gap-6">
        {/* Input */}
        <div className="space-y-3">
          {assets.map((asset, i) => (
            <div key={asset.name}>
              <div className="flex justify-between items-center mb-1">
                <label className="text-sm text-[#1F2937] font-medium">{asset.name}</label>
                <span className="nums text-sm font-semibold text-[#7C3AED]">{asset.weight.toFixed(1)}%</span>
              </div>
              <input
                type="range" min={0} max={100} step={0.5}
                value={asset.weight}
                onChange={(e) => setAssets((prev) => normalizeWeights(prev, i, parseFloat(e.target.value)))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer bg-gray-200 accent-[#7C3AED]
                  [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
                  [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-[#7C3AED] [&::-webkit-slider-thumb]:shadow-md"
              />
            </div>
          ))}
          <div className="border-t border-gray-100 pt-3 flex gap-3">
            <div className="flex-1">
              <label className="text-xs text-[#6B7280] block mb-1">总资产</label>
              <input type="number" value={totalAssets}
                onChange={(e) => setTotalAssets(Math.max(0, parseInt(e.target.value) || 0))}
                className="w-full px-3 py-1.5 rounded-xl border border-gray-200 text-sm nums bg-white/60
                  focus:outline-none focus:ring-2 focus:ring-[#7C3AED]/20 focus:border-[#7C3AED]" />
            </div>
            <div className="flex-1">
              <label className="text-xs text-[#6B7280] block mb-1">新增资金</label>
              <input type="number" value={newMoney}
                onChange={(e) => setNewMoney(Math.max(0, parseInt(e.target.value) || 0))}
                className="w-full px-3 py-1.5 rounded-xl border border-gray-200 text-sm nums bg-white/60
                  focus:outline-none focus:ring-2 focus:ring-[#7C3AED]/20 focus:border-[#7C3AED]" />
            </div>
          </div>
          <button onClick={handleCalculate} disabled={loading || totalAssets <= 0}
            className="w-full py-2 rounded-xl text-sm font-semibold text-white
              bg-gradient-to-r from-[#7C3AED] to-[#EC4899]
              hover:shadow-lg hover:shadow-purple-200 disabled:opacity-40 disabled:cursor-not-allowed
              transition-all duration-200 active:scale-[0.98]">
            {loading ? '计算中...' : '计算分配'}
          </button>
        </div>

        {/* Results */}
        <div>
          {error && <div className="text-[#EF4444] text-sm mb-2">{error}</div>}
          {data && <SimResults data={data} />}
          {!data && !loading && !error && (
            <div className="h-full flex flex-col items-center justify-center text-[#6B7280] text-sm py-8">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#7C3AED" strokeWidth="1.5" className="mb-2 opacity-40">
                <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
              调整参数后点击计算
            </div>
          )}
        </div>
      </div>
    </GlassCard>
  )
}

function SimResults({ data }: { data: SimulateResponse }) {
  return (
    <div className="space-y-2">
      {data.allocations.map((item) => {
        const before = (data.before_weights[item.asset] ?? 0) * 100
        const after = (data.after_weights[item.asset] ?? 0) * 100
        const diff = after - before
        return (
          <div key={item.asset} className="flex items-center justify-between py-1.5 px-3 rounded-xl bg-white/50 text-sm">
            <span className="font-medium text-[#1F2937] w-24">{item.asset}</span>
            <span className="nums text-[#6B7280] w-16 text-right">{before.toFixed(1)}%</span>
            <span className="text-[#6B7280]">→</span>
            <span className="nums font-medium text-[#1F2937] w-16 text-right">{after.toFixed(1)}%</span>
            <span className={`nums font-medium w-16 text-right ${diff > 0 ? 'text-[#10B981]' : diff < 0 ? 'text-[#EF4444]' : 'text-[#6B7280]'}`}>
              {diff > 0 ? '+' : ''}{diff.toFixed(2)}%
            </span>
            <span className="nums font-semibold text-[#1F2937] w-20 text-right">{fmt(item.amount)}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Trends Section ──
function TrendsSection() {
  const [selected, setSelected] = useState<IndexKey>('沪深300')
  const { data, loading, error } = useHistory(selected, 'pe', 5)
  const chartData: HistoryPoint[] = data ?? []

  return (
    <GlassCard title="PE 分位走势">
      <div className="flex flex-wrap gap-2 mb-4">
        {INDEX_KEYS.map((key) => (
          <button key={key} onClick={() => setSelected(key)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
              selected === key
                ? 'bg-[#7C3AED] text-white shadow-sm'
                : 'bg-white/60 text-[#6B7280] hover:text-[#1F2937] hover:bg-white border border-gray-100'
            }`}>
            {key}
          </button>
        ))}
      </div>
      <div className="w-full h-[220px]">
        {error ? (
          <div className="flex items-center justify-center h-full text-[#EF4444] text-sm">加载失败: {error}</div>
        ) : loading ? (
          <div className="flex items-center justify-center h-full text-[#6B7280] text-sm">加载中...</div>
        ) : chartData.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[#6B7280] text-sm">暂无数据</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tickFormatter={formatTickDate} tick={{ fontSize: 11, fill: '#6B7280' }} tickLine={false} axisLine={{ stroke: '#e5e7eb' }} interval="preserveStartEnd" minTickGap={60} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: '#6B7280' }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
              <Tooltip content={<LineTooltip />} />
              <ReferenceLine y={90} stroke="#EF4444" strokeDasharray="6 3" strokeWidth={1.5} label={{ value: '过热 90%', position: 'right', fill: '#EF4444', fontSize: 10 }} />
              <Line type="monotone" dataKey="value" stroke="#7C3AED" strokeWidth={2} dot={false} activeDot={{ r: 4, fill: '#7C3AED', stroke: 'white', strokeWidth: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </GlassCard>
  )
}

// ── Main Dashboard ──
export default function Dashboard() {
  const today = new Date()
  const dateStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  const { data, loading, error } = useReport(dateStr)

  if (error) {
    return (
      <div className="px-6 py-12">
        <GlassCard className="text-center py-12">
          <div className="text-[#EF4444] text-lg font-medium mb-2">数据加载失败</div>
          <div className="text-[#6B7280] text-sm">{error}</div>
          <p className="text-[#6B7280] text-xs mt-4">请确认后端服务正在运行</p>
        </GlassCard>
      </div>
    )
  }

  if (loading || !data) {
    return (
      <div className="p-6 space-y-4">
        <div className="flex items-center justify-between mb-2">
          <SkeletonCard className="!p-3 w-48" />
        </div>
        <div className="grid md:grid-cols-2 gap-4">
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <SkeletonTable rows={6} />
      </div>
    )
  }

  const { market_temp, portfolio_risk, allocations } = data

  return (
    <div className="p-4 sm:p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#7C3AED] to-[#EC4899] flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
          </div>
          <h1 className="text-lg font-semibold text-[#1F2937] tracking-tight">ETF Allocator</h1>
        </div>
        <span className="nums text-xs text-[#6B7280] bg-white/50 px-3 py-1.5 rounded-lg">{dateStr}</span>
      </div>

      {/* Warnings */}
      {data.warnings && data.warnings.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-3 text-sm text-amber-800">
          {data.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}

      {/* Row 1: Thermometer + Risk + Pie */}
      <div className="grid md:grid-cols-3 gap-4">
        {/* Market Thermometer */}
        <GlassCard title="市场温度计">
          <div className="space-y-3">
            <ProgressBar value={market_temp.hs300_pe_percentile} max={1}
              label={`沪深300 PE (5年) ${(market_temp.hs300_pe_percentile * 100).toFixed(0)}%`} showPercent height={8} />
            {market_temp.hs300_pe_percentile_long != null && (
              <ProgressBar value={market_temp.hs300_pe_percentile_long} max={1}
                label={`沪深300 PE (10年) ${(market_temp.hs300_pe_percentile_long * 100).toFixed(0)}%`} showPercent height={8} />
            )}
            <ProgressBar value={market_temp.all_a_pb_percentile} max={1}
              label={`全A PB ${(market_temp.all_a_pb_percentile * 100).toFixed(0)}%`} showPercent height={8} />
            <div className="flex items-center justify-between pt-2 border-t border-gray-100">
              <span className="text-xs text-[#6B7280]">
                权益 <span className="nums font-semibold text-[#1F2937]">{(market_temp.equity_ratio * 100).toFixed(0)}%</span>
                / 债券 <span className="nums font-semibold text-[#1F2937]">{(market_temp.bond_ratio * 100).toFixed(0)}%</span>
              </span>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusBg(market_temp.status)}`}>
                {market_temp.status}
              </span>
            </div>
          </div>
        </GlassCard>

        {/* Portfolio Risk */}
        <GlassCard title="组合风险">
          <div className="space-y-4">
            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs text-[#6B7280]">价值组 (白酒+银行+红利+沪深300)</span>
                <span className="nums text-xs text-[#1F2937]">
                  {(portfolio_risk.value_group_weight * 100).toFixed(0)}% / <span className="text-[#EF4444]">{(portfolio_risk.value_group_cap * 100).toFixed(0)}%</span>
                </span>
              </div>
              <div className="relative">
                <ProgressBar value={portfolio_risk.value_group_weight} max={portfolio_risk.value_group_cap} height={8} />
                <div className="absolute top-0 h-[8px] border-r-2 border-[#EF4444] z-10"
                  style={{ left: `${portfolio_risk.value_group_cap * 100}%` }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs text-[#6B7280]">成长组 (科创50)</span>
                <span className="nums text-xs text-[#1F2937]">
                  {(portfolio_risk.growth_group_weight * 100).toFixed(0)}% / <span className="text-[#EF4444]">{(portfolio_risk.growth_group_cap * 100).toFixed(0)}%</span>
                </span>
              </div>
              <div className="relative">
                <ProgressBar value={portfolio_risk.growth_group_weight} max={portfolio_risk.growth_group_cap} height={8} />
                <div className="absolute top-0 h-[8px] border-r-2 border-[#EF4444] z-10"
                  style={{ left: `${portfolio_risk.growth_group_cap * 100}%` }} />
              </div>
            </div>
            <div className="pt-2 border-t border-gray-100">
              <span className="text-xs text-[#6B7280]">
                下次再平衡: <span className="nums text-[#1F2937] font-medium">{portfolio_risk.next_rebalance_date}</span>
              </span>
            </div>
          </div>
        </GlassCard>

        {/* Pie chart */}
        <GlassCard title="分配占比">
          {data.allocation_summary ? (
            <div className="h-[200px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data.allocation_summary.filter((a) => a.amount > 0)}
                    dataKey="amount" nameKey="asset" cx="50%" cy="50%"
                    outerRadius={70} innerRadius={40}
                    label={({ name }: { name?: string }) => name ?? ''}
                    labelLine={{ stroke: '#9CA3AF' }}
                  >
                    {data.allocation_summary.filter((a) => a.amount > 0).map((entry, idx) => (
                      <Cell key={idx} fill={PIE_COLORS[entry.factor_group] || '#6B7280'} />
                    ))}
                  </Pie>
                  <Tooltip content={<PieTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="text-center py-6 text-[#6B7280] text-sm">暂无数据</div>
          )}
        </GlassCard>
      </div>

      {/* Row 2: Allocation Table */}
      <GlassCard title={`本月新增资金分配 (${fmt(data.new_money || 10000)})`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="text-left py-2.5 pr-4 text-[#6B7280] font-medium text-xs">资产</th>
              <th className="text-left py-2.5 px-3 text-[#6B7280] font-medium text-xs">代码</th>
              <th className="text-right py-2.5 px-3 text-[#6B7280] font-medium text-xs nums">分配金额</th>
              <th className="text-left py-2.5 px-3 text-[#6B7280] font-medium text-xs">权重上限</th>
              <th className="text-center py-2.5 px-3 text-[#6B7280] font-medium text-xs">机会分</th>
              <th className="text-left py-2.5 pl-3 text-[#6B7280] font-medium text-xs">触发原因</th>
            </tr>
          </thead>
          <tbody>
            {allocations.map((item) => (
              <tr key={item.asset} className="border-b border-gray-50 hover:bg-white/50 transition-colors">
                <td className="py-3 pr-4 font-medium text-[#1F2937]">{item.asset}</td>
                <td className="py-3 px-3 text-xs text-[#6B7280] font-mono">{item.code || '—'}</td>
                <td className="py-3 px-3 text-right nums font-semibold text-[#1F2937]">{fmt(item.amount)}</td>
                <td className="py-3 px-3 min-w-[130px]">
                  <div className="flex items-center gap-2">
                    <div className="flex-1"><ProgressBar value={item.current_weight} max={item.upper_limit} height={5} /></div>
                    <span className="nums text-xs text-[#6B7280] w-12 text-right">{(item.current_weight * 100).toFixed(1)}%</span>
                  </div>
                </td>
                <td className="py-3 px-3 text-center">
                  {item.opportunity_score !== null ? (
                    <span className="nums text-sm font-semibold" style={{ color: scoreColor(item.opportunity_score) }}>
                      {item.opportunity_score.toFixed(2)}
                    </span>
                  ) : (
                    <span className="text-[#6B7280] text-xs">—</span>
                  )}
                </td>
                <td className="py-3 pl-3 text-xs text-[#6B7280] max-w-[200px] truncate" title={item.trigger_reason}>
                  {item.trigger_reason}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </GlassCard>

      {/* Row 3: Simulator + Trends */}
      <div className="grid md:grid-cols-2 gap-4">
        <SimulateSection />
        <TrendsSection />
      </div>
    </div>
  )
}
