/**
 * Cyrus dashboard metrics API service.
 * Calls the Phase 6 /api/workspaces/:slug/cyrus/dashboard/* endpoints.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";
import type {
  DashboardMetrics,
  AgentHealthRow,
  PoolBudgetRow,
  GoalProgress,
} from "@/components/dashboard/types";

export class CyrusDashboardService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getMetrics(workspaceSlug: string, days = 7): Promise<DashboardMetrics> {
    return this.get(`/api/workspaces/${workspaceSlug}/cyrus/dashboard/metrics/?days=${days}`)
      .then((r) => r?.data)
      .catch((e) => { throw e?.response; });
  }

  async getAgentHealth(workspaceSlug: string): Promise<AgentHealthRow[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/cyrus/dashboard/agent-health/`)
      .then((r) => r?.data)
      .catch((e) => { throw e?.response; });
  }

  async getPoolBudgets(workspaceSlug: string): Promise<PoolBudgetRow[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/cyrus/dashboard/pool-budgets/`)
      .then((r) => r?.data)
      .catch((e) => { throw e?.response; });
  }

  async getGoalProgress(workspaceSlug: string): Promise<GoalProgress> {
    return this.get(`/api/workspaces/${workspaceSlug}/cyrus/dashboard/goals/`)
      .then((r) => r?.data)
      .catch((e) => { throw e?.response; });
  }
}

export const cyrusDashboardService = new CyrusDashboardService();
