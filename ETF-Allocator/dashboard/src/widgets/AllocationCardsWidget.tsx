import { motion } from 'framer-motion';
import type { BondStatus } from '../types';

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
  bondStatus?: BondStatus | null;
}

function scoreColor(s: number | null): string {
  if (s == null) return 'bg-chromatic-700';
  if (s >= 0.8) return 'bg-green-500';
  if (s >= 0.5) return 'bg-yellow-500';
  return 'bg-red-400';
}

/** 国债累积池进度条 */
function BondProgressCard({ status }: { status: BondStatus }) {
  const progress = Math.min(status.balance / status.min_purchase, 1);
  const progressPct = Math.round(progress * 100);
  // 预计还需几个月（按本月存入金额估算）
  const remaining = Math.max(0, status.min_purchase - status.balance);
  const monthsLeft = status.deposit_this_month > 0
    ? Math.ceil(remaining / status.deposit_this_month)
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.25, duration: 0.3 }}
      className="rounded-xl p-3 flex flex-col items-center gap-1.5 text-center border
        bg-amber-50 border-amber-200 shadow-sm col-span-2 sm:col-span-1"
    >
      <span className="text-xs font-bold text-amber-700">国债（累积中）</span>
      <span className="text-[10px] text-[#9CA3AF]">(511010)</span>

      {/* 进度条 */}
      <div className="w-full px-1">
        <div className="flex justify-between text-[10px] text-amber-600 mb-0.5">
          <span>¥{Math.round(status.balance).toLocaleString()}</span>
          <span>¥{Math.round(status.min_purchase).toLocaleString()}</span>
        </div>
        <div className="w-full h-2 bg-amber-100 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-amber-500 rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${progressPct}%` }}
            transition={{ duration: 0.6, ease: 'easeOut' }}
          />
        </div>
        <div className="text-[10px] text-amber-600 mt-0.5">
          {progressPct}% · 利息 ¥{status.total_interest.toFixed(1)}
        </div>
      </div>

      {/* 状态标签 */}
      {status.can_buy ? (
        <span className="text-[10px] font-medium text-green-600 bg-green-50 px-1.5 py-0.5 rounded">
          ✓ 可购买 {status.lots_available} 手
        </span>
      ) : (
        <span className="text-[10px] text-amber-500">
          {monthsLeft != null ? `约 ${monthsLeft} 个月后可买` : '等待累积'}
        </span>
      )}

      {/* 本月存入 */}
      {status.deposit_this_month > 0 && (
        <span className="text-[9px] text-[#9CA3AF]">
          本月存入 ¥{Math.round(status.deposit_this_month).toLocaleString()}
        </span>
      )}
    </motion.div>
  );
}

export function AllocationCardsWidget({ allocations, onSelect, selectedAsset, bondStatus }: Props) {
  const items = Object.entries(allocations);
  const isBond = (name: string) => name === '国债ETF';

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
      {items.map(([name, item], i) => (
        isBond(name) ? (
          // 国债ETF：如果本月执行了购买，显示金额卡片 + 累积进度；否则只显示累积进度
          bondStatus?.action_buy ? (
            <motion.div
              key={name}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06, duration: 0.3 }}
              className="rounded-xl p-3 flex flex-col items-center gap-2 text-center border
                bg-green-50 border-green-200 shadow-sm"
            >
              <span className="text-xs font-bold text-green-700">国债</span>
              <span className="text-[10px] text-[#9CA3AF]">(511010)</span>
              <span className="text-lg font-bold tabular-nums text-green-700">
                ¥{item.amount.toLocaleString('zh-CN')}
              </span>
              <span className="text-[10px] text-green-600">
                买入 {bondStatus.action_lots} 手
              </span>
              <span className="text-[9px] text-[#9CA3AF]">
                余额 ¥{Math.round(bondStatus.balance).toLocaleString()}
              </span>
            </motion.div>
          ) : bondStatus ? (
            <BondProgressCard key={name} status={bondStatus} />
          ) : (
            <motion.div
              key={name}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06, duration: 0.3 }}
              className="rounded-xl p-3 flex flex-col items-center gap-2 text-center border bg-amber-50 border-amber-200 shadow-sm"
            >
              <span className="text-xs font-bold text-amber-700">国债</span>
              <span className="text-[10px] text-[#9CA3AF]">({item.code ?? '511010'})</span>
              <span className="text-lg font-bold tabular-nums text-[#1F2937]">
                ¥{item.amount.toLocaleString('zh-CN')}
              </span>
              <span className="text-[10px] text-[#6B7280] leading-tight">{item.triggerReason}</span>
            </motion.div>
          )
        ) : (
          <motion.div
            key={name}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06, duration: 0.3 }}
            onClick={() => onSelect?.(name)}
            className={`rounded-xl p-3 flex flex-col items-center gap-2 text-center border transition-all cursor-pointer ${
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
        )
      ))}
    </div>
  );
}
