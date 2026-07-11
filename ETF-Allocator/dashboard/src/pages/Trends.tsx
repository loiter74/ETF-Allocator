import { useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import { useHistory } from '../hooks/useHistory'
import GlassCard from '../components/GlassCard'
import { SkeletonChart } from '../components/Skeleton'
import { INDEX_MAP } from '../types'
import type { HistoryPoint } from '../types'
import { historyToPercentileSeries } from '../widgets/utils'

type IndexKey = keyof typeof INDEX_MAP

const INDEX_KEYS: IndexKey[] = ['沪深300', '中证白酒', '中证银行', '中证红利', '科创50']

function formatTickDate(dateStr: string): string {
  return dateStr.slice(0, 7)
}

interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{ value: number }>
  label?: string
}

function CustomTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload || !payload.length) return null
  return (
    <div className="glass-card px-3 py-2 text-xs shadow-md">
      <div className="text-[#6B7280] mb-1">{label}</div>
      <div className="nums font-semibold text-[#1F2937]">
        {payload[0].value.toFixed(1)}%
      </div>
    </div>
  )
}

export default function Trends() {
  const [selected, setSelected] = useState<IndexKey>('沪深300')
  const { data, loading, error } = useHistory(selected, 'pe', 5)

  const handleSelect = (key: IndexKey) => {
    setSelected(key)
  }

  const chartData = historyToPercentileSeries((data ?? []) as HistoryPoint[])

  if (error) {
    return (
      <div className="px-6">
        <GlassCard className="text-center py-12">
          <div className="text-[#EF4444] text-lg font-medium mb-2">数据加载失败</div>
          <div className="text-[#6B7280] text-sm">{error}</div>
        </GlassCard>
      </div>
    )
  }

  return (
    <div className="px-4 sm:px-6 pb-6 sm:pb-8">
      {loading ? (
        <SkeletonChart />
      ) : (
        <GlassCard title="PE 分位走势">
          {/* Index selector */}
          <div className="flex flex-wrap gap-2 mb-6">
            {INDEX_KEYS.map((key) => (
              <button
                key={key}
                onClick={() => handleSelect(key)}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  selected === key
                    ? 'bg-[#7C3AED] text-white shadow-sm'
                    : 'bg-white/60 text-[#6B7280] hover:text-[#1F2937] hover:bg-white border border-gray-100'
                }`}
              >
                {key}
              </button>
            ))}
          </div>

          {/* Chart */}
          <div className="w-full h-[250px] sm:h-[380px]">
            {chartData.length === 0 ? (
              <div className="flex items-center justify-center h-full text-[#6B7280] text-sm">
                暂无数据
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={formatTickDate}
                    tick={{ fontSize: 11, fill: '#6B7280' }}
                    tickLine={false}
                    axisLine={{ stroke: '#e5e7eb' }}
                    interval="preserveStartEnd"
                    minTickGap={60}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 11, fill: '#6B7280' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine
                    y={90}
                    stroke="#EF4444"
                    strokeDasharray="6 3"
                    strokeWidth={1.5}
                    label={{
                      value: '过热阈值 90%',
                      position: 'right',
                      fill: '#EF4444',
                      fontSize: 11,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="percentilePct"
                    stroke="#7C3AED"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, fill: '#7C3AED', stroke: 'white', strokeWidth: 2 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="mt-4 text-xs text-[#6B7280] flex items-center gap-4">
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-[#7C3AED] inline-block" />
              {INDEX_MAP[selected].name} PE 分位
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-[#EF4444] inline-block border-dashed" style={{ borderTop: '1.5px dashed #EF4444', height: 0 }} />
              过热阈值
            </span>
          </div>
        </GlassCard>
      )}
    </div>
  )
}
