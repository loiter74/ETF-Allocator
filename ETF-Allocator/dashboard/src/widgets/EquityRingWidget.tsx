import { motion } from 'framer-motion';
import { ringColor } from './utils';

interface Props {
  equityRatio: number;
  bondRatio: number;
}

export function EquityRingWidget({ equityRatio, bondRatio }: Props) {
  const r = 56;
  const c = 2 * Math.PI * r;
  const color = ringColor(equityRatio);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-36 h-36">
        <svg viewBox="0 0 130 130" className="w-full h-full -rotate-90">
          <circle cx="65" cy="65" r={r} fill="none" stroke="#E5E7EB" strokeWidth="8" />
          <motion.circle
            cx="65" cy="65" r={r} fill="none"
            stroke={color} strokeWidth="8" strokeLinecap="round"
            strokeDasharray={`${c}`}
            initial={{ strokeDashoffset: c }}
            animate={{ strokeDashoffset: c * (1 - equityRatio) }}
            transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold tabular-nums" style={{ color }}>
            {Math.round(equityRatio * 100)}%
          </span>
          <span className="text-[10px] text-[#6B7280]">权益 · {Math.round(bondRatio * 100)}% 债</span>
        </div>
      </div>
    </div>
  );
}
