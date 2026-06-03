import { useState, useEffect, useCallback, useRef } from 'react';
import type { MonthlyReport, HistoryResponse } from '../types';

const BASE = '/api';
const POLL_MS = 10000;

export interface DashboardData {
  report: MonthlyReport | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;

  // Widget-ready data shapes
  thermometerData: {
    equityRatio: number;
    hs300PE: number | null;
    allAPB: number | null;
    label: string;
  };
  allocationData: {
    allocations: Record<string, { amount: number; triggerReason: string; opportunityScore: number | null }>;
  };
  equityRingData: {
    equityRatio: number;
    bondRatio: number;
  };
  riskData: {
    valueWeight: number;
    valueCap: number;
    growthWeight: number;
    growthCap: number;
  };
  scores: Record<string, number | null>;
  activityLog: { date: string; summary: string }[];
  valuationHistory: { date: string; pePercentile: number | null; pbPercentile: number | null }[];
}

function emptyDashboardData(): DashboardData {
  return {
    report: null, loading: true, error: null, refetch: () => {},
    thermometerData: { equityRatio: 0, hs300PE: null, allAPB: null, label: '加载中...' },
    allocationData: { allocations: {} },
    equityRingData: { equityRatio: 0, bondRatio: 0 },
    riskData: { valueWeight: 0, valueCap: 0.6, growthWeight: 0, growthCap: 0.15 },
    scores: {},
    activityLog: [],
    valuationHistory: [],
  };
}

function transformReport(r: MonthlyReport): Partial<DashboardData> {
  const temp = r.market_temp;
  const risk = r.portfolio_risk;
  const allocs: Record<string, { amount: number; triggerReason: string; opportunityScore: number | null }> = {};
  const scores: Record<string, number | null> = {};

  for (const a of r.allocations) {
    allocs[a.asset] = { amount: a.amount, triggerReason: a.trigger_reason, opportunityScore: a.opportunity_score, code: (a as any).code };
    scores[a.asset] = a.opportunity_score;
  }

  const statusLabels: Record<string, string> = {
    cool: '估值合理（<60%）', mild_cool: '中等偏高（60-80%）', strong_cool: '明显偏贵（80-90%）', overheat: '极端过热（>90%）',
    frozen: '温度计冻结中',
  };

  return {
    loading: false,
    thermometerData: {
      equityRatio: temp.equity_ratio,
      hs300PE: temp.hs300_pe_percentile,
      allAPB: temp.all_a_pb_percentile,
      label: statusLabels[temp.status] ?? temp.status,
    },
    allocationData: { allocations: allocs },
    equityRingData: { equityRatio: temp.equity_ratio, bondRatio: temp.bond_ratio },
    riskData: {
      valueWeight: risk.value_group_weight,
      valueCap: risk.value_group_cap,
      growthWeight: risk.growth_group_weight,
      growthCap: risk.growth_group_cap,
    },
    scores,
  };
}

export function useDashboardData(): DashboardData {
  const [report, setReport] = useState<MonthlyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<{ date: string; pePercentile: number | null; pbPercentile: number | null }[]>([]);
  const [activityLog, setActivityLog] = useState<{ date: string; summary: string }[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const fetchReport = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const today = new Date().toISOString().slice(0, 10);
      const res = await fetch(`${BASE}/report?date=${today}`, { signal: ctrl.signal });
      if (!res.ok) throw new Error(`API ${res.status}`);
      const json: MonthlyReport = await res.json();
      if (!ctrl.signal.aborted) {
        setReport(json);
        setLoading(false);
        setError(null);

        // 累积活动日志：每次 API 查询更新本条日期状态
        if (json.allocations.length > 0) {
          const mkt = json.market_temp;
          const equityPct = Math.round(mkt.equity_ratio * 100);
          const targetEquity = json.new_money * mkt.equity_ratio;
          const actualEquity = json.allocations
            .filter((a: any) => a.asset !== '国债ETF')
            .reduce((s: number, a: any) => s + a.amount, 0);
          const gap = targetEquity - actualEquity;
          const activeCount = json.allocations.filter((a: any) => a.amount > 0).length;
          const labels: Record<string, string> = {
            cool: '估值合理', mild_cool: '中等偏高', strong_cool: '明显偏贵', overheat: '极端过热', frozen: '温度冻结',
          };
          const statusLabel = labels[mkt.status] ?? mkt.status;
          const gapStr = gap > 10 ? ` | 约束截留 ¥${Math.round(gap).toLocaleString()}` : '';
          const summary = `查询成功 · 权益 ${equityPct}% · ${statusLabel} · ${activeCount} 项分配${gapStr}`;
          setActivityLog(prev => {
            const idx = prev.findIndex(e => e.date === json.date);
            if (idx >= 0) {
              const next = [...prev];
              next[idx] = { date: json.date, summary };
              return next;
            }
            return [...prev.slice(-19), { date: json.date, summary }];
          });
        }
      }
    } catch (err) {
      if (!ctrl.signal.aborted) {
        setError((err as Error).message);
        setLoading(false);
      }
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const ctrl = new AbortController();
      const [peRes, pbRes] = await Promise.all([
        fetch(`${BASE}/history?index=000300&field=pe`, { signal: ctrl.signal }),
        fetch(`${BASE}/history?index=000985&field=pb`, { signal: ctrl.signal }),
      ]);
      const pe: HistoryResponse = await peRes.json();
      const pb: HistoryResponse = await pbRes.json();

      const peMap = new Map(pe.data.map(d => [d.date, d.percentile]));
      const pbMap = new Map(pb.data.map(d => [d.date, d.percentile]));
      const allDates = [...new Set([...peMap.keys(), ...pbMap.keys()])].sort();

      setHistory(allDates.map(d => ({
        date: d,
        pePercentile: peMap.get(d) ?? null,
        pbPercentile: pbMap.get(d) ?? null,
      })));
    } catch { /* history is optional */ }
  }, []);

  useEffect(() => {
    fetchReport();
    fetchHistory();
    const timer = setInterval(fetchReport, POLL_MS);
    return () => {
      clearInterval(timer);
      abortRef.current?.abort();
    };
  }, [fetchReport, fetchHistory]);

  const dash = emptyDashboardData();
  if (report) Object.assign(dash, transformReport(report));
  dash.report = report;
  dash.loading = loading;
  dash.error = error;
  dash.refetch = fetchReport;
  dash.valuationHistory = history;
  dash.activityLog = activityLog;

  return dash;
}
