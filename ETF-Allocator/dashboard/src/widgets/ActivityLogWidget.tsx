import { motion } from 'framer-motion';

interface Entry {
  date: string;
  summary: string;
}

interface Props {
  history: Entry[];
}

export function ActivityLogWidget({ history }: Props) {
  const entries = history.slice(-8).reverse();
  return (
    <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
      {entries.map((entry, i) => (
        <motion.div
          key={entry.date + '-' + i}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.05 }}
          className="flex gap-3 text-xs"
        >
          <span className="text-[#6B7280] tabular-nums whitespace-nowrap pt-0.5">
            {i === 0 && '🔄 '}{entry.date}
          </span>
          <span className="text-[#1F2937] leading-relaxed">{entry.summary}</span>
        </motion.div>
      ))}
      {history.length === 0 && <div className="text-[#9CA3AF] text-xs">暂无记录</div>}
    </div>
  );
}
