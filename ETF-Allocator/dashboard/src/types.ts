export interface MarketThermometer {
  hs300_pe_percentile: number;
  all_a_pb_percentile: number;
  hs300_pe_percentile_long?: number | null;
  all_a_pb_percentile_long?: number | null;
  equity_ratio: number;
  bond_ratio: number;
  status: string;
}

export interface PortfolioRisk {
  value_group_weight: number;
  value_group_cap: number;
  growth_group_weight: number;
  growth_group_cap: number;
  next_rebalance_date: string;
}

export interface AllocationItem {
  asset: string;
  code?: string;
  amount: number;
  current_weight: number;
  upper_limit: number;
  opportunity_score: number | null;
  trigger_reason: string;
}

export interface AllocationSummary {
  asset: string;
  amount: number;
  percentage: number;
  factor_group: string;
}

/** 国债累积池状态（BondAccumulator 输出） */
export interface BondStatus {
  balance: number;             // 累积池当前余额
  min_purchase: number;        // 最低买入门槛 (14,000)
  total_interest: number;      // 累计逆回购利息
  can_buy: boolean;            // 本月是否可触发购买
  lots_available: number;      // 可买手数
  deposit_this_month: number;  // 本月存入金额
  interest_this_month: number; // 本月利息
  action_buy: boolean;         // 本月实际是否执行了购买
  action_lots: number;         // 本月购买手数
  action_amount: number;       // 本月购买金额
}

export interface MonthlyReport {
  date: string;
  new_money?: number;
  total_assets?: number;
  market_temp: MarketThermometer;
  portfolio_risk: PortfolioRisk;
  allocations: AllocationItem[];
  allocation_summary?: AllocationSummary[];
  warnings?: string[];
  bond_status?: BondStatus;
}

export interface SimulateRequest {
  date: string;
  new_money: number;
  total_assets: number;
  current_weights: Record<string, number>;
}

export interface SimulateResponse {
  date: string;
  new_money: number;
  total_assets: number;
  new_total: number;
  allocations: AllocationItem[];
  before_weights: Record<string, number>;
  after_weights: Record<string, number>;
  bond_status?: BondStatus;
}

export interface HistoryPoint {
  date: string;
  value?: number;
  percentile?: number;
}

export interface HistoryResponse {
  index: string;
  field: string;
  data: HistoryPoint[];
}

export interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

export interface InvestmentRecord {
  id: number;
  investment_date: string;
  amount: number;
  allocations: Record<string, number>;
  note: string;
  created_at: string;
}

export interface InvestmentSummary {
  count: number;
  total_amount: number;
  last_date: string | null;
  last_amount: number | null;
}

export interface InvestmentResponse {
  records: InvestmentRecord[];
  summary: InvestmentSummary;
}

export interface InvestmentCreateRequest {
  investment_date: string;
  allocations: Record<string, number>;
  note: string;
}

export const INDEX_MAP: Record<string, { name: string; code: string }> = {
  沪深300: { name: '沪深300', code: '000300' },
  中证白酒: { name: '中证白酒', code: '399997' },
  中证银行: { name: '中证银行', code: '399986' },
  中证红利: { name: '中证红利', code: '000922' },
  科创50: { name: '科创50', code: '000688' },
};

/** ETF名称 → 跟踪指数代码（与 config/settings.py::ASSETS 的 tracking_index 一致） */
export const ETF_TRACKING_INDEX: Record<string, string> = {
  '白酒ETF': '399997',
  '银行ETF': '399986',
  '红利ETF': '000922',
  '沪深300ETF': '000300',
  '科创50ETF': '000688',
};
