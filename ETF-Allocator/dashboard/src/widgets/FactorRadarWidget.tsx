import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer } from 'recharts';

interface Props {
  scores: Record<string, number | null>;
}

const LABELS: Record<string, string> = {
  '白酒ETF': '白酒', '银行ETF': '银行', '红利ETF': '红利',
  '沪深300ETF': '沪深300', '科创50ETF': '科创50',
};

export function FactorRadarWidget({ scores }: Props) {
  // 包含所有资产，null → 0（雷达上可见但灰色标注数据不足）
  const data = Object.entries(LABELS).map(([key, label]) => ({
    name: label,
    score: scores[key] ?? 0,
    hasData: scores[key] != null,
    rawScore: scores[key],
  }));

  /** 根据机会分值返回颜色：绿(>0.7) → 黄(0.4-0.7) → 橙红(<0.4) */
  function scoreTickColor(s: number | null): string {
    if (s == null) return '#D1D5DB';
    if (s >= 0.7) return '#16A34A';
    if (s >= 0.4) return '#CA8A04';
    return '#DC2626';
  }

  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="65%">
          <PolarGrid stroke="#E5E7EB" />
          <PolarAngleAxis
            dataKey="name"
            tick={({ payload, x, y, ...rest }: any) => {
              const d = data.find(d => d.name === payload.value);
              const color = d?.hasData ? '#374151' : '#D1D5DB';
              const showScore = d?.hasData && d.rawScore != null;
              return (
                <text x={x} y={y} fill={color} fontSize={11} textAnchor="middle" dominantBaseline="central">
                  <tspan x={x} dy={-6} fill={color}>{payload.value}</tspan>
                  {showScore && (
                    <tspan x={x} dy={14} fill={scoreTickColor(d.rawScore!)} fontSize={12} fontWeight="bold">
                      {Math.round(d.rawScore! * 100)}分
                    </tspan>
                  )}
                </text>
              );
            }}
          />
          <PolarRadiusAxis angle={90} domain={[0, 1]} tick={false} axisLine={false} />
          <Radar name="机会分" dataKey="score" stroke="#7C3AED" fill="#7C3AED" fillOpacity={0.12} dot={{ fill: '#7C3AED', r: 3 }} />
        </RadarChart>
      </ResponsiveContainer>
      <div className="text-center text-xs text-[#D1D5DB] mt-1">灰色 = 数据不足</div>
    </div>
  );
}
