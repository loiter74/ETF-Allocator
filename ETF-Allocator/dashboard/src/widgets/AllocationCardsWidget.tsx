import { motion } from 'framer-motion';

interface AllocItem {
  amount: number;
  triggerReason: string;
  opportunityScore: number | null;
  code?: string;
}

interface Props {
  allocations: Record<string, AllocItem>;
  onSelect?: (asset: string) => void;
  selectedAsset?: string;
}

function scoreColor(s: number | null): string {
  if (s == null) return 'bg-chromatic-700';
  if (s >= 0.8) return 'bg-green-500';
  if (s >= 0.5) return 'bg-yellow-500';
  return 'bg-red-400';
}

export function AllocationCardsWidget({ allocations, onSelect, selectedAsset }: Props) {
  const items = Object.entries(allocations);
  const isBond = (name: string) => name === '国债ETF';
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
      {items.map(([name, item], i) => (
        <motion.div
          key={name}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.06, duration: 0.3 }}
          onClick={() => !isBond(name) && onSelect?.(name)}
          className={`rounded-xl p-3 flex flex-col items-center gap-2 text-center border transition-all ${
            isBond(name) ? '' : 'cursor-pointer'
          } ${
            selectedAsset === name
              ? 'bg-[#7C3AED]/10 border-[#7C3AED] ring-2 ring-[#7C3AED]/20 shadow-md scale-[1.02]'
              : item.amount > 0
                ? 'bg-white border-gray-100 shadow-sm hover:shadow-md hover:border-[#7C3AED]/30'
                : 'bg-gray-50 border-gray-100 opacity-60'
          }`}
        >
          <span className="text-xs font-bold text-[#7C3AED]">{name.replace('ETF', '')}</span>
          <span className="text-[10px] text-[#9CA3AF]">({item.code})</span>
          <span className="text-lg font-bold tabular-nums text-[#1F2937]">
            ¥{item.amount.toLocaleString('zh-CN')}
          </span>
          <span className="text-[10px] text-[#6B7280] leading-tight">{item.triggerReason}</span>
          <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-white ${scoreColor(item.opportunityScore)}`}>
            {item.opportunityScore != null ? Math.round(item.opportunityScore * 100) : '—'}
          </span>
        </motion.div>
      ))}
    </div>
  );
}
