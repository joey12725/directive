/**
 * Executive Dashboard — main page component.
 *
 * Fetches from all Phase 6 dashboard endpoints via SWR and renders:
 * - Top strip: Utilization, Active Agents, Agent Health, Pending Approvals
 * - Left column: Activity Summary, Active Blockers, Alignment Drift
 * - Right/Bottom: Cost Tracker chart, Goal KPI cards
 */

import { useCallback, useState } from "react";
import useSWR from "swr";
import { Skeleton } from "@plane/propel/skeleton";
import { Button } from "@plane/propel/button";
import { Bot } from "lucide-react";
import { UserGreetingsView } from "@/components/home/user-greetings";
import { useUser } from "@/hooks/store/user";
import { cyrusDashboardService } from "@/services/cyrus-dashboard.service";
import {
  UtilizationCard,
  ActiveAgentsCard,
  AgentHealthCard,
  PendingApprovalsCard,
} from "./metric-cards";
import { ActivitySummaryCard } from "./activity-summary-card";
import { ActiveBlockersList } from "./active-blockers-list";
import { AlignmentDriftPanel } from "./alignment-drift-panel";
import { CostTracker } from "./cost-tracker";
import { GoalKPICards } from "./goal-kpi-cards";
import { CyrusAgentModal } from "./cyrus-agent-modal";
import type {
  DashboardMetrics,
  AgentHealthRow,
  PoolBudgetRow,
  GoalProgress,
} from "./types";

interface ExecutiveDashboardProps {
  workspaceSlug: string;
}

const EMPTY_METRICS: DashboardMetrics = {
  token_consumption: [],
  cost_incurred: [],
  session_stats: { total_sessions: 0, completed_sessions: 0, success_rate_pct: 0, avg_duration_seconds: 0 },
  active_alerts: { active_blockers: 0, pending_approvals: 0, alignment_drift: 0 },
};
const EMPTY_AGENTS: AgentHealthRow[] = [];
const EMPTY_POOLS: PoolBudgetRow[] = [];
const EMPTY_GOALS: GoalProgress = { status_distribution: {}, total_goals: 0, approaching_deadlines: [], kpis: [] };

function DashboardSkeleton() {
  return (
    <div className="p-6 space-y-6">
      <Skeleton>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton.Item key={i} height="96px" width="100%" />
          ))}
        </div>
      </Skeleton>
      <Skeleton>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <Skeleton.Item height="200px" width="100%" />
            <Skeleton.Item height="150px" width="100%" />
          </div>
          <div>
            <Skeleton.Item height="300px" width="100%" />
          </div>
        </div>
      </Skeleton>
      <Skeleton>
        <Skeleton.Item height="280px" width="100%" />
      </Skeleton>
    </div>
  );
}

export function ExecutiveDashboard({ workspaceSlug }: ExecutiveDashboardProps) {
  const [days, setDays] = useState(7);
  const [isAgentModalOpen, setIsAgentModalOpen] = useState(false);
  const { data: currentUser } = useUser();

  const { data: metrics, isLoading: metricsLoading } = useSWR<DashboardMetrics>(
    `CYRUS_METRICS_${workspaceSlug}_${days}`,
    () => cyrusDashboardService.getMetrics(workspaceSlug, days)
  );

  const { data: agents, isLoading: agentsLoading } = useSWR<AgentHealthRow[]>(
    `CYRUS_AGENT_HEALTH_${workspaceSlug}`,
    () => cyrusDashboardService.getAgentHealth(workspaceSlug)
  );

  const { data: pools, isLoading: poolsLoading } = useSWR<PoolBudgetRow[]>(
    `CYRUS_POOL_BUDGETS_${workspaceSlug}`,
    () => cyrusDashboardService.getPoolBudgets(workspaceSlug)
  );

  const { data: goals, isLoading: goalsLoading } = useSWR<GoalProgress>(
    `CYRUS_GOALS_${workspaceSlug}`,
    () => cyrusDashboardService.getGoalProgress(workspaceSlug)
  );

  const isLoading = metricsLoading || agentsLoading || poolsLoading || goalsLoading;

  // Safe defaults — all components handle empty/zero data
  const m = metrics ?? EMPTY_METRICS;
  const a = agents ?? EMPTY_AGENTS;
  const p = pools ?? EMPTY_POOLS;
  const g = goals ?? EMPTY_GOALS;

  const handleTimeWindowChange = useCallback((newDays: number) => {
    setDays(newDays);
  }, []);

  if (isLoading && !metrics && !agents) return <DashboardSkeleton />;

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-6 space-y-6">
        {/* Greeting + Header */}
        <div className="flex items-center justify-between">
          <div className="flex-1">
            {currentUser && <UserGreetingsView user={currentUser} />}
          </div>
          <Button
            variant="primary"
            size="base"
            prependIcon={<Bot />}
            onClick={() => setIsAgentModalOpen(true)}
          >
            Cyrus Agent
          </Button>
        </div>

        {/* ============================================================ */}
        {/* TOP STRIP — 4 metric cards                                   */}
        {/* ============================================================ */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <UtilizationCard pools={p} workspaceSlug={workspaceSlug} />
          <ActiveAgentsCard agents={a} workspaceSlug={workspaceSlug} />
          <AgentHealthCard agents={a} workspaceSlug={workspaceSlug} />
          <PendingApprovalsCard alerts={m.active_alerts} workspaceSlug={workspaceSlug} />
        </div>

        {/* ============================================================ */}
        {/* MIDDLE — Left column + Right column                          */}
        {/* ============================================================ */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column: 2/3 width */}
          <div className="lg:col-span-2 space-y-4">
            <ActivitySummaryCard stats={m.session_stats} workspaceSlug={workspaceSlug} onTimeWindowChange={handleTimeWindowChange} />
            <ActiveBlockersList alerts={m.active_alerts} />
            <AlignmentDriftPanel agents={a} />
          </div>

          {/* Right column: 1/3 width — Cost chart */}
          <div className="space-y-4">
            <CostTracker data={m.cost_incurred} workspaceSlug={workspaceSlug} />
          </div>
        </div>

        {/* ============================================================ */}
        {/* BOTTOM — Goal KPI Cards                                      */}
        {/* ============================================================ */}
        <GoalKPICards kpis={g.kpis} deadlines={g.approaching_deadlines} />
      </div>

      {/* Cyrus Agent Modal */}
      <CyrusAgentModal
        isOpen={isAgentModalOpen}
        onClose={() => setIsAgentModalOpen(false)}
        workspaceSlug={workspaceSlug}
      />
    </div>
  );
}
