/** 可视化 Widget 共用纯函数。不依赖 React，可直接单元测试。 */

export interface Zone {
  color: string;
  label: string;
}

/**
 * equityRatio（权益投资上限比例）→ 温度色区。
 *
 * 映射逻辑（对应 ds.v1.2 §七 温度计 4 档）：
 *   >= 95% → 绿色"估值合理"（双指标<60%，Tier 0）
 *   >= 60% → 蓝色"轻度降温"（60-80%，Tier 1）
 *   >= 35% → 橙色"明显偏贵"（80-90%，Tier 2）
 *   <  35% → 红色"极端过热"（>90%，Tier 3）
 */
export function zoneFor(equityRatio: number): Zone {
  if (equityRatio >= 0.95) return { color: '#10B981', label: '估值合理' };
  if (equityRatio >= 0.60) return { color: '#3B82F6', label: '轻度降温' };
  if (equityRatio >= 0.35) return { color: '#F97316', label: '明显偏贵' };
  return { color: '#EF4444', label: '极端过热' };
}

/**
 * 权益仓位环的颜色。
 *    >= 70% → 绿色
 *    40-70% → 蓝色
 *    <  40% → 橙色
 */
export function ringColor(equityRatio: number): string {
  if (equityRatio >= 0.70) return '#10B981';
  if (equityRatio >= 0.40) return '#3B82F6';
  return '#F97316';
}

/**
 * 风险条颜色（当前权重/上限）。
 *    < 80%  → 绿色
 *    80-95% → 黄色
 *    > 95%  → 红色
 */
export function riskBarColor(ratio: number): string {
  if (ratio < 0.80) return '#10B981';
  if (ratio < 0.95) return '#F59E0B';
  return '#EF4444';
}

/**
 * 机会分 → 徽章颜色。
 *    >= 0.8 → 绿色
 *    >= 0.5 → 黄色
 *    >= 0.0 → 红色
 *    null   → 灰色
 */
export function scoreBadgeColor(s: number | null): string {
  if (s == null) return '#6B7280';
  if (s >= 0.8) return '#10B981';
  if (s >= 0.5) return '#F59E0B';
  return '#EF4444';
}
