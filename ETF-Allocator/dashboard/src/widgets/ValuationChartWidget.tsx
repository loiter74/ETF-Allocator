import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';
import { InfoTip } from '../components/InfoTip';

interface Point { date: string; pePercentile: number | null; pbPercentile: number | null; }

interface Props {
  history: Point[];
  selectedAsset: string;
  years: number;
  onYearsChange: (y: number) => void;
}

const INDEX_LABELS: Record<string, string> = {
  '白酒ETF': '中证白酒 PE/PB',
  '银行ETF': '中证银行 PB',
  '红利ETF': '中证红利 PE/PB',
  '沪深300ETF': '沪深300 PE/PB',
  '科创50ETF': '科创50 PE/PB',
};

const YEAR_OPTIONS = [2, 5, 10];

export function ValuationChartWidget({ history, selectedAsset, years, onYearsChange }: Props) {
  const title = INDEX_LABELS[selectedAsset] ?? selectedAsset;
  const data = history.map(p => ({
    date: p.date.slice(5),
    PE: p.pePercentile != null ? Math.round(p.pePercentile * 100) : null,
    PB: p.pbPercentile != null ? Math.round(p.pbPercentile * 100) : null,
  }));

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-[#6B7280] flex items-center gap-0.5">{title}
          <InfoTip text={`PE/PB 历史分位走势\n当前估值在最近N年中的百分位\n用 expanding window（滚动起始点）计算\n横线：60%🟡 80%🟠 90%🔴\n数据来源：index_valuation表`} />
        </span>
        <div className="flex gap-1 items-center">
          {YEAR_OPTIONS.map(y => (
            <button
              key={y}
              onClick={() => onYearsChange(y)}
              className={`px-2 py-0.5 text-xs rounded-md transition cursor-pointer ${
                years === y
                  ? 'bg-[#7C3AED] text-white'
                  : 'bg-gray-100 text-[#6B7280] hover:bg-gray-200'
              }`}
            >
              {y}年
            </button>
          ))}
          <InfoTip text={`分位窗口 = expanding\n取最近{years}年历史数据\n∩ 当前日期为截止日\n不包含未来（publish_date ≤ 决策日）`} />
        </div>
      </div>
      <div className="w-full h-72">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <CartesianGrid stroke="#E5E7EB" strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fill: '#9CA3AF', fontSize: 10 }} />
            <YAxis domain={[0, 100]} tick={{ fill: '#9CA3AF', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#fff', border: '1px solid #E5E7EB', borderRadius: 8, fontSize: 12 }} />
            <ReferenceLine y={60} stroke="#F59E0B" strokeDasharray="4 4" />
            <ReferenceLine y={80} stroke="#F97316" strokeDasharray="4 4" />
            <ReferenceLine y={90} stroke="#EF4444" strokeDasharray="4 4" />
            <Area type="monotone" dataKey="PE" stroke="#7C3AED" fill="#7C3AED" fillOpacity={0.1} connectNulls />
            <Area type="monotone" dataKey="PB" stroke="#10B981" fill="#10B981" fillOpacity={0.1} connectNulls />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
