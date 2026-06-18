/** Response shapes for the /v1/* endpoints the console consumes. Loose by design —
 *  the backend is the source of truth; these cover the fields the UI reads. */

export type Rec = "BUY" | "SELL" | "HOLD";

export interface SignalDetail {
  score: number;
  weight: number;
  value: number | null;
  label: string;
}

export interface PositionSizing {
  recommended_pct: number;
  kelly_pct?: number;
  vol_target_pct?: number;
  risk_budget_pct?: number;
  reason?: string;
}

export interface UpcomingEvent {
  days_to_event: number;
  impact: string;
  title: string;
  region: string;
  event_date: string;
}

export interface Decision {
  symbol: string;
  cached: boolean;
  recommendation: Rec;
  confidence: number;
  risk_level: string;
  weighted_score: number;
  position_sizing?: PositionSizing | null;
  calibrated_win_prob?: number | null;
  market_regime?: string | null;
  upcoming_event?: UpcomingEvent | null;
  signals: Record<string, SignalDetail>;
  forecast: { date: string; predicted_close: number; lower: number; upper: number }[];
  sentiment_score: number | null;
  current_close?: number | null;
  days_to_earnings?: number | null;
  bull_case: string;
  bear_case: string;
  explanation: string;
}

export interface Committee {
  symbol: string;
  cached: boolean;
  views: Record<string, string>;
  votes: Record<string, Rec | null>;
  risk_officer: string;
  vetoed: boolean;
  veto_reasons: string[];
  engine_recommendation: Rec;
  final_recommendation: Rec;
  llm_available?: boolean;
}

export interface RegimeRow {
  date: string;
  regime: string;
  reason: string;
  index_symbol: string;
  index_close: number | null;
  vix: number | null;
  breadth_pct: number | null;
}
export interface RegimeResponse {
  us: RegimeRow | null;
  india: RegimeRow | null;
}

export interface MarketEvent {
  date: string;
  type: string;
  region: string;
  impact: string;
  title: string;
}
export interface EventsResponse {
  events: MarketEvent[];
}

export interface Alert {
  id: string;
  symbol: string;
  alert_type: string;
  value: number;
  threshold: number;
  detected_at: string;
}

export interface RiskReport {
  source: string;
  positions: number;
  total_value: number;
  weights: Record<string, number>;
  sector_exposure?: { by_sector: Record<string, number>; hhi: number; top_sector: string | null; top_sector_pct: number };
  country_exposure?: Record<string, number>;
  market_cap_exposure?: Record<string, number>;
  correlation?: { avg_pairwise: number; max_pair: { symbols: string[]; correlation: number } } | null;
  var?: {
    confidence: number;
    var_pct: number;
    cvar_pct: number;
    var_value: number;
    cvar_value: number;
    annualized_vol: number;
  } | null;
  risk_score?: { score: number; level: string; components: Record<string, number> };
  warnings?: string[];
}

export interface StopPosition {
  symbol: string;
  entry: number;
  current: number;
  stop_level: number;
  stop_pct: number;
  trailing: boolean;
  breached: boolean;
  distance_pct: number | null;
  stop_pl_pct: number;
  recommended: boolean;
}
export interface StopsResponse {
  source: string;
  positions: StopPosition[];
  breached_count: number;
  breached: string[];
  warnings?: string[];
}

export interface WatchlistItem {
  symbol: string;
  quantity: number | null;
  cost_basis: number | null;
  current_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  recommendation: Rec | null;
  confidence: number | null;
  risk_level: string | null;
  suggested_position_pct: number | null;
  sentiment_score: number | null;
}
export interface WatchlistResponse {
  items: WatchlistItem[];
  totals: {
    positions: number;
    market_value: number;
    cost_value: number;
    unrealized_pnl: number;
    unrealized_pnl_pct: number | null;
  };
}

export interface Backtest {
  symbol: string;
  window_days: number;
  // Daily mode returns `total_return`; discrete/capital mode returns `net_return`.
  net_return?: number;
  total_return?: number;
  gross_return?: number;
  cost_drag?: number;
  win_rate?: number | null;
  sharpe_ratio?: number | null;
  max_drawdown?: number | null;
  trades?: number;
  // Daily mode keys items as `cumulative`; discrete mode as `equity`.
  equity_curve?: { date: string; equity?: number; cumulative?: number }[];
  assumptions?: string[];
  [k: string]: unknown;
}

export interface MlModelRow {
  version: string;
  trained_at: string;
  n_samples: number;
  oos_auc: number | null;
  oos_hit_rate: number | null;
  oos_brier: number | null;
  promoted: boolean;
}
export interface MlModelResponse {
  active: MlModelRow | null;
  latest: MlModelRow | null;
  signal_weight: number;
  in_use: boolean;
  history: (MlModelRow | null)[];
}

export interface DriftResponse {
  verdict: string;
  evaluated_count: number;
  drift: {
    status: string;
    recent: { count: number; hit_rate: number } | null;
    baseline: { count: number; hit_rate: number } | null;
    delta: number | null;
  };
}

export interface ReportRow {
  created_at: string;
  query: string;
  response: string;
}

export interface IndiaSignals {
  date: string | null;
  fii_net_cr: number | null;
  dii_net_cr: number | null;
  pcr: number | null;
  gift_nifty_pct: number | null;
  source: string | null;
  india_flow: { score: number; weight: number; value: number | null; label: string };
}
