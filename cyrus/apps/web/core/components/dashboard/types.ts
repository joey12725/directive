/**
 * Types matching the Phase 6 dashboard API response shapes.
 */

// GET /api/v1/workspaces/:slug/dashboard/metrics/
export interface DashboardMetrics {
  token_consumption: TokenConsumptionRow[];
  cost_incurred: CostIncurredRow[];
  session_stats: SessionStats;
  active_alerts: ActiveAlerts;
}

export interface TokenConsumptionRow {
  date: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface CostIncurredRow {
  date: string;
  pool: string;
  cost_usd: number;
}

export interface SessionStats {
  total_sessions: number;
  completed_sessions: number;
  success_rate_pct: number;
  avg_duration_seconds: number;
}

export interface ActiveAlerts {
  active_blockers: number;
  pending_approvals: number;
  alignment_drift: number;
}

// GET /api/v1/workspaces/:slug/dashboard/agent-health/
export interface AgentHealthRow {
  id: string;
  name: string;
  agent_type: string;
  status: "online" | "offline" | "degraded" | "errored";
  last_heartbeat: string | null;
  heartbeat_age_seconds: number | null;
  active_sessions: number;
  sessions_7d: number;
  success_rate_7d_pct: number;
  failed_7d: number;
  total_tokens_7d: number;
  total_cost_7d_usd: number;
}

// GET /api/v1/workspaces/:slug/dashboard/pool-budgets/
export interface PoolBudgetRow {
  id: string;
  name: string;
  provider: string;
  pool_type: string;
  budget_period: string;
  budget_limit_usd: number;
  spent_usd: number;
  remaining_usd: number;
  utilization_pct: number;
  daily_burn_usd: number;
  runway_days: number | null;
  total_tokens: number;
  usage_records: number;
  rate_limited_records: number;
}

// GET /api/v1/workspaces/:slug/dashboard/goals/
export interface GoalProgress {
  status_distribution: Record<string, number>;
  total_goals: number;
  approaching_deadlines: GoalDeadline[];
  kpis: GoalKPI[];
}

export interface GoalDeadline {
  id: string;
  name: string;
  deadline: string;
  days_remaining: number;
  is_overdue: boolean;
}

export interface GoalKPI {
  goal_id: string;
  goal_name: string;
  kpi_name: string;
  unit: string;
  current_value: number | null;
  last_collected: string | null;
  history_points: number;
}
