import type { ElementType } from 'react';
import { ThermometerWidget } from './ThermometerWidget';
import { AllocationCardsWidget } from './AllocationCardsWidget';
import { EquityRingWidget } from './EquityRingWidget';
import { FactorRadarWidget } from './FactorRadarWidget';
import { RiskBarWidget } from './RiskBarWidget';
import { ValuationChartWidget } from './ValuationChartWidget';
import { ActivityLogWidget } from './ActivityLogWidget';
import { ProfitProtectionWidget } from './ProfitProtectionWidget';

export interface WidgetMeta {
  id: string;
  component: ElementType;
  title: string;
  defaultSize: { w: number; h: number };
  minSize: { w: number; h: number };
}

export const WIDGET_REGISTRY: Record<string, WidgetMeta> = {
  thermometer:    { id: 'thermometer',    component: ThermometerWidget,    title: '市场温度计',  defaultSize: { w: 3, h: 3 }, minSize: { w: 2, h: 2 } },
  equityRing:     { id: 'equityRing',     component: EquityRingWidget,     title: '权益仓位',    defaultSize: { w: 3, h: 3 }, minSize: { w: 2, h: 2 } },
  allocation:     { id: 'allocation',     component: AllocationCardsWidget, title: '本月分配',   defaultSize: { w: 6, h: 3 }, minSize: { w: 4, h: 2 } },
  activityLog:    { id: 'activityLog',    component: ActivityLogWidget,    title: '活动日志',    defaultSize: { w: 3, h: 4 }, minSize: { w: 2, h: 3 } },
  factorRadar:    { id: 'factorRadar',    component: FactorRadarWidget,    title: '因子雷达',    defaultSize: { w: 4, h: 4 }, minSize: { w: 3, h: 3 } },
  riskBar:        { id: 'riskBar',        component: RiskBarWidget,        title: '因子组约束',  defaultSize: { w: 6, h: 2 }, minSize: { w: 4, h: 2 } },
  valuationChart: { id: 'valuationChart', component: ValuationChartWidget, title: '估值分位',    defaultSize: { w: 6, h: 4 }, minSize: { w: 4, h: 3 } },
  profitProtection: { id: 'profitProtection', component: ProfitProtectionWidget, title: '盈利收获与交易计划', defaultSize: { w: 12, h: 8 }, minSize: { w: 6, h: 5 } },
};

export const DEFAULT_LAYOUTS = {
  lg: [
    { i: 'thermometer',    x: 0, y: 0, w: 3, h: 3 },
    { i: 'equityRing',     x: 3, y: 0, w: 3, h: 3 },
    { i: 'activityLog',    x: 9, y: 0, w: 3, h: 4 },
    { i: 'allocation',     x: 0, y: 3, w: 6, h: 3 },
    { i: 'factorRadar',    x: 0, y: 6, w: 4, h: 4 },
    { i: 'valuationChart', x: 4, y: 6, w: 8, h: 4 },
    { i: 'riskBar',        x: 0, y: 10, w: 12, h: 2 },
  ],
};
