import { motion } from 'framer-motion';
import { zoneFor } from './utils';
import { InfoTip } from '../components/InfoTip';

interface Props {
  equityRatio: number;  // 0-1
  hs300PE: number | null;
  allAPB: number | null;
  label: string;
}

export function ThermometerWidget({ equityRatio, hs300PE, allAPB, label }: Props) {
  const r = 70;
  const circumference = 2 * Math.PI * r;
  const fill = equityRatio * circumference;
  const zone = zoneFor(equityRatio);

  const pePct = hs300PE != null ? Math.round(hs300PE * 100) : null;
  const pbPct = allAPB != null ? Math.round(allAPB * 100) : null;

  return (
    <div className="flex flex-col items-center gap-3">
      {/* SVG 径向仪表 */}
      <div className="relative w-44 h-44">
        <svg viewBox="0 0 160 160" className="w-full h-full -rotate-90">
          <circle cx="80" cy="80" r={r} fill="none" stroke="#E5E7EB" strokeWidth="10" />
          <motion.circle
            cx="80" cy="80" r={r} fill="none"
            stroke={zone.color} strokeWidth="10" strokeLinecap="round"
            strokeDasharray={`${circumference}`}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: circumference - fill }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <motion.span
            key={equityRatio}
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="text-4xl font-bold tabular-nums"
            style={{ color: zone.color }}
          >
            {Math.round(equityRatio * 100)}%
          </motion.span>
          <span className="text-xs text-[#6B7280] mt-1 flex items-center gap-0.5">
            权益上限
            <InfoTip text={`权益上限 = 温度计输出\n4档对应：双<60%→100% · 60-80%→70% · 80-90%→40% · >90%→30%\n不一致→冻结上期值 · 首调用→${Math.round((0.70)*100)}%`} />
          </span>
        </div>
      </div>

      <span className="text-xs text-[#6B7280] font-medium">{label}</span>

      <div className="text-xs text-[#6B7280] space-x-3">
        <span className="inline-flex items-center gap-0.5">
          沪深300 PE: {pePct != null ? `${pePct}%` : '—'}
          <InfoTip text={`沪深300 PE 分位\n= 当前PE在最近5年历史中的百分位\n用 expanding window 防未来函数\n例：91% → 比历史上91%的时间贵`} />
        </span>
        <span className="inline-flex items-center gap-0.5">
          全A PB: {pbPct != null ? `${pbPct}%` : '—'}
          <InfoTip text={`全A 等权 PB 分位\n= 全市场PB在最近5年历史中的百分位\n用expanding window防未来函数\n例：30% → 比历史上30%的时间贵（估值合理）`} />
        </span>
      </div>
    </div>
  );
}
