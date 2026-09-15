/**
 * Cyrus CRUD service for goals, agents, pools, sessions, and KPIs.
 * Uses /api/ (session-auth) endpoints, not /api/v1/ (API key auth).
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export interface PaginatedResponse<T> {
  results: T[];
}

const h = (e: unknown) => { throw (e as { response?: unknown })?.response; };

export class CyrusCrudService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  // ================================================================
  // Goals
  // ================================================================
  async listGoals(ws: string, status?: string): Promise<PaginatedResponse<Record<string, unknown>>> {
    const qs = status ? `?status=${status}` : "";
    return this.get(`/api/workspaces/${ws}/cyrus/goals/${qs}`).then((r) => r?.data).catch(h);
  }

  async getGoal(ws: string, goalId: string): Promise<Record<string, unknown>> {
    return this.get(`/api/workspaces/${ws}/cyrus/goals/${goalId}/`).then((r) => r?.data).catch(h);
  }

  async createGoal(ws: string, data: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.post(`/api/workspaces/${ws}/cyrus/goals/`, data).then((r) => r?.data).catch(h);
  }

  async updateGoal(ws: string, goalId: string, data: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.patch(`/api/workspaces/${ws}/cyrus/goals/${goalId}/`, data).then((r) => r?.data).catch(h);
  }

  async deleteGoal(ws: string, goalId: string): Promise<void> {
    return this.delete(`/api/workspaces/${ws}/cyrus/goals/${goalId}/`).then(() => undefined).catch(h);
  }

  // ================================================================
  // Goal KPIs
  // ================================================================
  async listGoalKPIs(ws: string, goalId: string): Promise<PaginatedResponse<Record<string, unknown>>> {
    return this.get(`/api/workspaces/${ws}/cyrus/goals/${goalId}/kpis/`).then((r) => r?.data).catch(h);
  }

  async createGoalKPI(ws: string, goalId: string, data: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.post(`/api/workspaces/${ws}/cyrus/goals/${goalId}/kpis/`, data).then((r) => r?.data).catch(h);
  }

  async updateGoalKPI(ws: string, goalId: string, kpiId: string, data: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.patch(`/api/workspaces/${ws}/cyrus/goals/${goalId}/kpis/${kpiId}/`, data).then((r) => r?.data).catch(h);
  }

  async deleteGoalKPI(ws: string, goalId: string, kpiId: string): Promise<void> {
    return this.delete(`/api/workspaces/${ws}/cyrus/goals/${goalId}/kpis/${kpiId}/`).then(() => undefined).catch(h);
  }

  // ================================================================
  // Agents, Pools, Sessions (unchanged)
  // ================================================================
  async listAgents(ws: string): Promise<PaginatedResponse<Record<string, unknown>>> {
    return this.get(`/api/workspaces/${ws}/cyrus/agents/`).then((r) => r?.data).catch(h);
  }

  async listPools(ws: string): Promise<PaginatedResponse<Record<string, unknown>>> {
    return this.get(`/api/workspaces/${ws}/cyrus/pools/`).then((r) => r?.data).catch(h);
  }

  async listSessions(ws: string): Promise<PaginatedResponse<Record<string, unknown>>> {
    return this.get(`/api/workspaces/${ws}/cyrus/sessions/`).then((r) => r?.data).catch(h);
  }
}

export const cyrusCrudService = new CyrusCrudService();
