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
  balance: number;             // 累积池当前余额（模拟存入后；预演值）
  min_purchase: number;        // 最低买入门槛 (14,000)
  total_interest: number;      // 累计逆回购利息
  can_buy: boolean;            // 本月是否可触发购买
  lots_available: number;      // 可买手数
  deposit_this_month: number;  // 本月存入金额
  interest_this_month: number; // 本月利息
  action_buy: boolean;         // 本月实际是否执行了购买
  action_lots: number;         // 本月购买手数
  action_amount: number;       // 本月购买金额
  // 真实状态（未模拟，来自持久化文件）—— 面板同时展示真实 + 预演
  current_balance?: number;      // 真实累积池余额
  current_total_interest?: number; // 真实累计利息
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

export interface PortfolioPositionInput {
  asset: string;
  code: string;
  shares: number;
  price: number;
  market_value?: number;
  average_cost?: number | null;
  is_equity: boolean;
}

export interface PortfolioSnapshotInput {
  snapshot_date: string;
  price_date: string;
  new_money: number;
  account_cash: number;
  bond_pool_cash: number;
  reverse_repo_cash: number;
  equity_pending_cash: number;
  positions: PortfolioPositionInput[];
}

export interface TradePlanPreviewRequest {
  snapshot: PortfolioSnapshotInput;
}

export interface TradeOrder {
  side: 'BUY' | 'SELL';
  asset: string;
  code: string;
  reason_codes: string[];
  shares: number;
  reference_price: number;
  estimated_price: number;
  gross_amount: number;
  commission: number;
  slippage_cost: number;
  cash_effect: number;
  mandatory: boolean;
  shadow: boolean;
  allocation_stages: string[];
  // 各分配阶段给本资产分到的金额明细 {stage: amount}（仅 BUY 单有）
  stage_breakdown?: Record<string, number>;
}

export interface PortfolioExposure {
  total_assets: number;
  managed_total: number;
  managed_weights: Record<string, number>;
  group_weights: Record<string, number>;
  account_equity_ratio: number;
  defense_ratio: number;
  unknown_value: number;
}

export interface TradeCashLedger {
  opening_cash: number;
  new_money: number;
  sell_net_proceeds: number;
  buy_cash_outflow: number;
  closing_cash: number;
  bond_pool_before: number;
  bond_pool_deposit: number;
  bond_pool_released: number;
  bond_pool_after: number;
  equity_pending_before: number;
  equity_pending_after: number;
  free_cash_after: number;
  total_commission: number;
  total_slippage: number;
  cash_identity_error: number;
}

export interface TradePlan {
  plan_id: string;
  snapshot_date: string;
  phase: 'complete' | 'sell_preview' | string;
  formal_sells: TradeOrder[];
  shadow_sells: TradeOrder[];
  buys: TradeOrder[];
  warnings: string[];
  before: PortfolioExposure;
  after: PortfolioExposure;
  cash_ledger: TradeCashLedger | null;
  pending_buy_recalculation: boolean;
  legacy_allocation_only: boolean;
}

export interface ProfitProtectionThresholds {
  activation_return: number;
  drawdown_trigger: number;
  off_months_exit: number;
  partial_sell_fraction: number;
}

export interface ProfitProtectionStatus {
  mode: 'shadow' | 'live' | string;
  active: boolean;
  cycle_id: number;
  high_watermark: number;
  off_months: number;
  on_months: number;
  pending_trigger: string | null;
  profit_return: number | null;
  drawdown_from_high: number | null;
  activated_this_month: boolean;
  trend_on: boolean;
  opportunity_score: number | null;
  triggered: boolean;
  trigger_reason_codes: string[];
  thresholds: ProfitProtectionThresholds;
}

export interface TradePlanPreviewResponse {
  snapshot_total_assets: number;
  trade_plan: TradePlan;
  protection_status: ProfitProtectionStatus;
  read_only: boolean;
}

export type SnapshotFieldSource = 'ocr' | 'deepseek' | 'local_parser' | 'market_data' | 'user' | 'missing' | string;

export interface SnapshotImportField<T = number | string> {
  value: T | null;
  confidence: number;
  source: SnapshotFieldSource;
  evidence: string;
  value_date: string | null;
}

export interface SnapshotImportPosition {
  asset: SnapshotImportField<string>;
  code: SnapshotImportField<string>;
  shares: SnapshotImportField<number>;
  price: SnapshotImportField<number>;
  average_cost: SnapshotImportField<number>;
  market_value: SnapshotImportField<number>;
  is_equity: boolean;
  warnings: string[];
}

export interface SnapshotImportDraft {
  snapshot_date: SnapshotImportField<string>;
  account_cash: SnapshotImportField<number>;
  positions: SnapshotImportPosition[];
}

export interface OcrTextSegment {
  name: string;
  text: string;
  ocr_confidence?: number | null;
}

export interface SnapshotImportRequest {
  snapshot_date?: string;
  ocr_texts: OcrTextSegment[];
}

export interface SnapshotImportResponse {
  draft: SnapshotImportDraft;
  provider: 'deepseek' | 'local_parser' | string;
  model: string | null;
  warnings: string[];
  input_characters: number;
  read_only: boolean;
  image_uploaded: boolean;
}

export interface SnapshotOcrConfig {
  deepseek_enabled: boolean;
  structuring_provider: 'deepseek' | 'local_parser' | string;
  model: string | null;
  image_upload: false;
  ocr_location: 'browser' | string;
  accepted_image_types: string[];
  max_files: number;
  max_file_bytes: number;
  max_total_bytes: number;
  max_segment_characters: number;
  max_total_characters: number;
  privacy_notice: string;
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
