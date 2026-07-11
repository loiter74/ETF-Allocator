import { describe, it, expect } from 'vitest';
import { zoneFor, ringColor, riskBarColor, scoreBadgeColor, historyToPercentileSeries } from './utils';

describe('historyToPercentileSeries', () => {
  it('plots percentile instead of raw valuation values', () => {
    const result = historyToPercentileSeries([
      { date: '2026-06-01', percentile: 0.724 },
      { date: '2026-06-02' },
    ]);
    expect(result).toHaveLength(1);
    expect(result[0].date).toBe('2026-06-01');
    expect(result[0].percentilePct).toBeCloseTo(72.4);
  });

  it('clamps malformed percentile values to the chart domain', () => {
    expect(historyToPercentileSeries([
      { date: 'low', percentile: -0.2 },
      { date: 'high', percentile: 1.4 },
    ])).toEqual([
      { date: 'low', percentilePct: 0 },
      { date: 'high', percentilePct: 100 },
    ]);
  });
});

// ── zoneFor — 温度计色区 ──

describe('zoneFor', () => {
  it('equityRatio=0.30（极端过热）→ 红色', () => {
    const z = zoneFor(0.30);
    expect(z.color).toBe('#EF4444');
    expect(z.label).toBe('极端过热');
  });

  it('equityRatio=0.40（明显偏贵）→ 橙色', () => {
    const z = zoneFor(0.40);
    expect(z.color).toBe('#F97316');
    expect(z.label).toBe('明显偏贵');
  });

  it('equityRatio=0.70（轻度降温）→ 蓝色', () => {
    const z = zoneFor(0.70);
    expect(z.color).toBe('#3B82F6');
    expect(z.label).toBe('轻度降温');
  });

  it('equityRatio=1.00（估值合理）→ 绿色', () => {
    const z = zoneFor(1.00);
    expect(z.color).toBe('#10B981');
    expect(z.label).toBe('估值合理');
  });

  it('边界：equityRatio=0.95 → 绿色', () => {
    expect(zoneFor(0.95).color).toBe('#10B981');
  });

  it('边界：equityRatio=0.60 → 蓝色', () => {
    expect(zoneFor(0.60).color).toBe('#3B82F6');
  });

  it('边界：equityRatio=0.35 → 橙色', () => {
    expect(zoneFor(0.35).color).toBe('#F97316');
  });

  it('边界：equityRatio=0.34 → 红色', () => {
    expect(zoneFor(0.34).color).toBe('#EF4444');
  });

  it('equityRatio=0 → 红色（极端情况）', () => {
    expect(zoneFor(0).color).toBe('#EF4444');
  });
});

// ── ringColor — 权益仓位环 ──

describe('ringColor', () => {
  it('0.70 → 绿色', () => expect(ringColor(0.70)).toBe('#10B981'));
  it('0.40 → 蓝色', () => expect(ringColor(0.40)).toBe('#3B82F6'));
  it('0.39 → 橙色', () => expect(ringColor(0.39)).toBe('#F97316'));
  it('1.00 → 绿色', () => expect(ringColor(1.00)).toBe('#10B981'));
  it('0.00 → 橙色', () => expect(ringColor(0.00)).toBe('#F97316'));
});

// ── riskBarColor — 风险条 ──

describe('riskBarColor', () => {
  it('<80% → 绿色', () => expect(riskBarColor(0.5)).toBe('#10B981'));
  it('80-95% → 黄色', () => expect(riskBarColor(0.85)).toBe('#F59E0B'));
  it('>95% → 红色', () => expect(riskBarColor(0.99)).toBe('#EF4444'));
  it('边界 0.80 → 黄色', () => expect(riskBarColor(0.80)).toBe('#F59E0B'));
  it('边界 0.95 → 红色', () => expect(riskBarColor(0.95)).toBe('#EF4444'));
});

// ── scoreBadgeColor — 机会分徽章 ──

describe('scoreBadgeColor', () => {
  it('0.80 → 绿色', () => expect(scoreBadgeColor(0.80)).toBe('#10B981'));
  it('0.50 → 黄色', () => expect(scoreBadgeColor(0.50)).toBe('#F59E0B'));
  it('0.49 → 红色', () => expect(scoreBadgeColor(0.49)).toBe('#EF4444'));
  it('null → 灰色', () => expect(scoreBadgeColor(null)).toBe('#6B7280'));
  it('0.00 → 红色', () => expect(scoreBadgeColor(0)).toBe('#EF4444'));
});
