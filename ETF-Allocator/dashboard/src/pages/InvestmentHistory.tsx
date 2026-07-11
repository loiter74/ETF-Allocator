import { useState, type FormEvent } from 'react';
import GlassCard from '../components/GlassCard';
import { SkeletonCard } from '../components/Skeleton';
import { useInvestmentRecords } from '../hooks/useInvestmentRecords';
import { formatLocalDate } from '../lib/utils';

const INVESTMENT_ASSETS = [
  { name: '白酒ETF', label: '白酒', code: '161725' },
  { name: '银行ETF', label: '银行', code: '512800' },
  { name: '红利ETF', label: '红利', code: '515080' },
  { name: '沪深300ETF', label: '沪深300', code: '510300' },
  { name: '科创50ETF', label: '科创50', code: '588000' },
  { name: '国债ETF', label: '国债', code: '511010' },
] as const;

function emptyAllocationInputs(): Record<string, string> {
  return Object.fromEntries(INVESTMENT_ASSETS.map(asset => [asset.name, '']));
}

function formatAmount(amount: number | null): string {
  if (amount == null) return '暂无';
  return `¥${amount.toLocaleString('zh-CN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}`;
}

export default function InvestmentHistory() {
  const {
    data,
    loading,
    saving,
    deletingId,
    error,
    createRecord,
    deleteRecord,
  } = useInvestmentRecords();
  const [investmentDate, setInvestmentDate] = useState(formatLocalDate);
  const [allocationInputs, setAllocationInputs] = useState<Record<string, string>>(emptyAllocationInputs);
  const [note, setNote] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const summary = data?.summary ?? {
    count: 0,
    total_amount: 0,
    last_date: null,
    last_amount: null,
  };
  const allocationValues = Object.fromEntries(
    INVESTMENT_ASSETS.map(asset => [asset.name, Number(allocationInputs[asset.name] || 0)]),
  );
  const totalAmount = Object.values(allocationValues).reduce((sum, value) => sum + value, 0);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const invalidAsset = INVESTMENT_ASSETS.find(asset => {
      const value = allocationValues[asset.name];
      return !Number.isFinite(value) || value < 0;
    });
    if (invalidAsset) {
      setLocalError(`${invalidAsset.label}的金额不能小于 0`);
      return;
    }
    if (totalAmount <= 0) {
      setLocalError('请至少填写一个大于 0 的资产投入金额');
      return;
    }

    setLocalError(null);
    const saved = await createRecord({
      investment_date: investmentDate,
      allocations: allocationValues,
      note: note.trim(),
    });
    if (saved) {
      setAllocationInputs(emptyAllocationInputs());
      setNote('');
    }
  };

  const handleDelete = async (recordId: number) => {
    const deleted = await deleteRecord(recordId);
    if (deleted) setConfirmDeleteId(null);
  };

  return (
    <main className="px-4 sm:px-6 pb-6 sm:pb-8">
      <div className="mb-4">
        <h1 className="text-xl sm:text-2xl font-semibold text-[#1F2937]">资金记录</h1>
        <p className="mt-1 text-sm text-[#6B7280]">
          只记录已经实际投入的资金，月度配置计算不会自动写入这里。
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 mb-4">
        <GlassCard className="p-4">
          <div className="text-xs text-[#6B7280]">最近一次投入</div>
          <div className="mt-2 text-2xl font-semibold nums text-[#7C3AED]">
            {formatAmount(summary.last_amount)}
          </div>
          <div className="mt-1 text-xs nums text-[#9CA3AF]">
            {summary.last_date ?? '尚未记录'}
          </div>
        </GlassCard>
        <GlassCard className="p-4">
          <div className="text-xs text-[#6B7280]">累计投入</div>
          <div className="mt-2 text-2xl font-semibold nums text-[#1F2937]">
            {formatAmount(summary.total_amount)}
          </div>
          <div className="mt-1 text-xs text-[#9CA3AF]">按已确认记录累计</div>
        </GlassCard>
        <GlassCard className="p-4">
          <div className="text-xs text-[#6B7280]">投入次数</div>
          <div className="mt-2 text-2xl font-semibold nums text-[#1F2937]">
            {summary.count}
          </div>
          <div className="mt-1 text-xs text-[#9CA3AF]">条历史记录</div>
        </GlassCard>
      </div>

      {(localError || error) && (
        <div role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {localError || error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(280px,0.7fr)_minmax(0,1.3fr)] gap-4 sm:gap-6">
        <GlassCard title="录入投入记录">
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="investment-date" className="block text-sm font-medium text-[#1F2937] mb-1">
                投入日期
              </label>
              <input
                id="investment-date"
                type="date"
                value={investmentDate}
                max={formatLocalDate()}
                onChange={event => setInvestmentDate(event.target.value)}
                required
                className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-[#1F2937] focus:outline-none focus:ring-2 focus:ring-[#7C3AED]/20 focus:border-[#7C3AED]"
              />
            </div>
            <fieldset>
              <div className="mb-2 flex items-baseline justify-between gap-3">
                <legend className="text-sm font-medium text-[#1F2937]">各资产投入明细</legend>
                <span className="nums text-sm font-semibold text-[#7C3AED]">
                  合计 {formatAmount(totalAmount)}
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {INVESTMENT_ASSETS.map(asset => (
                  <label key={asset.name} className="rounded-xl border border-gray-100 bg-white/70 px-3 py-2">
                    <span className="mb-1 flex items-baseline justify-between gap-2">
                      <span className="text-sm font-medium text-[#1F2937]">{asset.label}</span>
                      <span className="nums text-[11px] text-[#9CA3AF]">{asset.code}</span>
                    </span>
                    <span className="relative block">
                      <span className="absolute left-0 top-1/2 -translate-y-1/2 text-sm text-[#6B7280]">¥</span>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        aria-label={`${asset.label}投入金额`}
                        value={allocationInputs[asset.name]}
                        onChange={event => setAllocationInputs(current => ({
                          ...current,
                          [asset.name]: event.target.value,
                        }))}
                        placeholder="0"
                        className="w-full border-0 bg-transparent py-0.5 pl-5 pr-0 text-sm nums text-[#1F2937] placeholder:text-[#9CA3AF] focus:outline-none"
                      />
                    </span>
                  </label>
                ))}
              </div>
              <p className="mt-2 text-xs text-[#9CA3AF]">没有投入的项目可留空，记录总额会按上面明细自动相加。</p>
            </fieldset>
            <div>
              <label htmlFor="investment-note" className="block text-sm font-medium text-[#1F2937] mb-1">
                备注 <span className="font-normal text-[#9CA3AF]">可选</span>
              </label>
              <input
                id="investment-note"
                type="text"
                maxLength={200}
                value={note}
                onChange={event => setNote(event.target.value)}
                placeholder="例如：七月工资结余"
                className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-[#1F2937] placeholder:text-[#9CA3AF] focus:outline-none focus:ring-2 focus:ring-[#7C3AED]/20 focus:border-[#7C3AED]"
              />
            </div>
            <button
              type="submit"
              disabled={saving}
              className="w-full rounded-xl bg-gradient-to-r from-[#7C3AED] to-[#EC4899] py-2.5 text-sm font-semibold text-white transition hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? '保存中...' : totalAmount > 0 ? `确认已投入 ${formatAmount(totalAmount)}` : '确认已投入'}
            </button>
          </form>
        </GlassCard>

        {loading && !data ? (
          <SkeletonCard />
        ) : (
          <GlassCard title="历史投入">
            {data?.records.length ? (
              <div className="space-y-2">
                {data.records.map(record => (
                  <div key={record.id} className="rounded-xl border border-gray-100 bg-white/70 px-3 py-3 sm:px-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                          <span className="nums text-sm text-[#6B7280]">{record.investment_date}</span>
                          <strong className="nums text-lg text-[#1F2937]">{formatAmount(record.amount)}</strong>
                        </div>
                        <p className="mt-1 text-xs text-[#6B7280] break-words">
                          {record.note || '无备注'}
                        </p>
                      </div>
                      {confirmDeleteId === record.id ? (
                        <div className="flex shrink-0 items-center gap-2">
                          <button
                            type="button"
                            onClick={() => void handleDelete(record.id)}
                            disabled={deletingId === record.id}
                            className="text-xs font-medium text-red-600 disabled:opacity-50"
                          >
                            {deletingId === record.id ? '删除中' : '确认'}
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmDeleteId(null)}
                            className="text-xs text-[#6B7280]"
                          >
                            取消
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteId(record.id)}
                          className="shrink-0 text-xs text-[#9CA3AF] hover:text-red-500 transition-colors"
                        >
                          删除
                        </button>
                      )}
                    </div>
                    {Object.keys(record.allocations).length > 0 ? (
                      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-gray-100 pt-3 sm:grid-cols-3">
                        {INVESTMENT_ASSETS.map(asset => {
                          const assetAmount = record.allocations[asset.name] ?? 0;
                          return (
                            <div key={asset.name} className="flex items-baseline justify-between gap-2">
                              <span className="text-xs text-[#6B7280]">{asset.label}</span>
                              <span className={`nums text-xs font-medium ${assetAmount > 0 ? 'text-[#1F2937]' : 'text-[#9CA3AF]'}`}>
                                {formatAmount(assetAmount)}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="mt-3 border-t border-gray-100 pt-3 text-xs text-[#9CA3AF]">
                        旧记录未记录分项
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-14 text-center">
                <div className="text-sm font-medium text-[#1F2937]">还没有投入记录</div>
                <p className="mt-2 text-xs text-[#6B7280]">在左侧补录以往投入，之后就能看到上次金额和累计投入。</p>
              </div>
            )}
          </GlassCard>
        )}
      </div>
    </main>
  );
}
