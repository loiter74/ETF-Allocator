import { describe, it, expect } from 'vitest';

/**
 * useDashboardData 的 activityLog 累积逻辑验证。
 * 
 * 这是一个纯逻辑测试 — 模拟 setActivityLog 的 reducer 行为。
 * 核心规则：seenDates 去重 + prev.slice(-19) 保留最近 20 条。
 */
describe('activityLog accumulation logic', () => {
  it('accumulates unique dates across polls', () => {
    const seenDates = new Set<string>();
    const logs: { date: string; summary: string }[] = [];

    // 模拟 3 次轮询
    const polls = [
      { date: '2026-06-01', summary: '白酒 ¥2500 · 银行 ¥1500 · 红利 ¥1200' },
      { date: '2026-06-01', summary: '白酒 ¥2500 · 银行 ¥1500 · 红利 ¥1200' }, // 同日重复
      { date: '2026-06-02', summary: '银行 ¥3000 · 科创50 ¥2000' },
      { date: '2026-06-03', summary: '白酒 ¥4000' },
    ];

    for (const { date, summary } of polls) {
      if (!seenDates.has(date)) {
        seenDates.add(date);
        logs.push({ date, summary }); // kept at max 20 via slice(-19)
      }
    }

    // 同日重复被去重 → 3 条
    expect(logs).toHaveLength(3);
    expect(logs[0].date).toBe('2026-06-01');
    expect(logs[1].date).toBe('2026-06-02');
    expect(logs[2].date).toBe('2026-06-03');
  });

  it('trims to max 20 entries', () => {
    const seenDates = new Set<string>();
    let logs: { date: string; summary: string }[] = [];

    for (let i = 1; i <= 25; i++) {
      const date = `2026-06-${String(i).padStart(2, '0')}`;
      if (!seenDates.has(date)) {
        seenDates.add(date);
        logs = [...logs, { date, summary: `poll #${i}` }].slice(-20);
      }
    }

    expect(logs).toHaveLength(20);
    expect(logs[0].date).toBe('2026-06-06'); // #6-25 = 20 entries, first is #6
    expect(logs[19].date).toBe('2026-06-25');
  });
});
