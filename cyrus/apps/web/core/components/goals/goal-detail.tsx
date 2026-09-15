/**
 * GoalDetail — full detail page for a single goal.
 * Shows goal info, KPI table with history charts, linked sessions.
 */

import { useState, useCallback } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Target,
  Plus,
  Pencil,
  Trash2,
  ChevronDown,
  ChevronRight,
  Play,
  Layers,
  Calendar,
} from "lucide-react";
import useSWR, { useSWRConfig } from "swr";
import { Badge } from "@plane/propel/badge";
import { Button } from "@plane/propel/button";
import { Card } from "@plane/propel/card";
import { Skeleton } from "@plane/propel/skeleton";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@plane/propel/table";
import { cyrusCrudService } from "@/services/cyrus-crud.service";
import { GoalFormModal } from "./goal-form-modal";
import { KPIFormModal } from "./kpi-form-modal";
import { KPIHistoryChart } from "./kpi-history-chart";

const STATUS_VARIANT: Record<string, "success" | "warning" | "neutral"> = {
  active: "success",
  paused: "warning",
  archived: "neutral",
};

interface GoalDetailProps {
  workspaceSlug: string;
  goalId: string;
}

export function GoalDetail({ workspaceSlug, goalId }: GoalDetailProps) {
  const { mutate } = useSWRConfig();
  const cacheKey = `CYRUS_GOAL_${workspaceSlug}_${goalId}`;

  const { data: goal, isLoading, error } = useSWR(
    cacheKey,
    () => cyrusCrudService.getGoal(workspaceSlug, goalId)
  );

  // Modal state
  const [editGoalOpen, setEditGoalOpen] = useState(false);
  const [addKPIOpen, setAddKPIOpen] = useState(false);
  const [editKPI, setEditKPI] = useState<Record<string, unknown> | null>(null);
  const [expandedKPIs, setExpandedKPIs] = useState<Set<string>>(new Set());
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const refreshGoal = useCallback(() => {
    mutate(cacheKey);
    mutate(`CYRUS_GOALS_LIST_${workspaceSlug}`);
  }, [cacheKey, mutate, workspaceSlug]);

  const handleUpdateGoal = async (data: Record<string, unknown>) => {
    await cyrusCrudService.updateGoal(workspaceSlug, goalId, data);
    refreshGoal();
  };

  const handleDeleteGoal = async () => {
    await cyrusCrudService.deleteGoal(workspaceSlug, goalId);
    mutate(`CYRUS_GOALS_LIST_${workspaceSlug}`);
    window.history.back();
  };

  const handleCreateKPI = async (data: Record<string, unknown>) => {
    await cyrusCrudService.createGoalKPI(workspaceSlug, goalId, data);
    refreshGoal();
  };

  const handleUpdateKPI = async (data: Record<string, unknown>) => {
    if (!editKPI) return;
    await cyrusCrudService.updateGoalKPI(workspaceSlug, goalId, String(editKPI.id), data);
    setEditKPI(null);
    refreshGoal();
  };

  const handleDeleteKPI = async (kpiId: string) => {
    await cyrusCrudService.deleteGoalKPI(workspaceSlug, goalId, kpiId);
    setDeleteConfirm(null);
    refreshGoal();
  };

  const toggleKPIExpand = (id: string) => {
    setExpandedKPIs((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="p-6">
        <Skeleton>
          <Skeleton.Item height="40px" width="50%" />
          <Skeleton.Item height="20px" width="30%" className="mt-3" />
          <Skeleton.Item height="200px" width="100%" className="mt-6" />
          <Skeleton.Item height="300px" width="100%" className="mt-4" />
        </Skeleton>
      </div>
    );
  }

  if (error || !goal) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <p className="text-body-sm text-tertiary">Goal not found.</p>
        <Button variant="secondary" className="mt-4" onClick={() => window.history.back()}>Go Back</Button>
      </div>
    );
  }

  const kpis = (goal.kpis as Record<string, unknown>[]) || [];
  const sessions = (goal.recent_sessions as Record<string, unknown>[]) || [];
  const deadline = goal.deadline ? new Date(String(goal.deadline)) : null;

  return (
    <div className="h-full overflow-y-auto">
      {/* Top bar */}
      <div className="sticky top-0 z-10 bg-surface-0 border-b border-subtle px-6 py-3 flex items-center gap-3">
        <Button variant="ghost" size="sm" prependIcon={<ArrowLeft />} onClick={() => window.history.back()}>
          Back
        </Button>
        <div className="h-4 w-px bg-subtle" />
        <Target className="size-4 text-tertiary" />
        <h1 className="text-body-md-medium text-primary truncate">{String(goal.name)}</h1>
        <Badge variant={STATUS_VARIANT[String(goal.status)] ?? "neutral"} size="base">
          {String(goal.status)}
        </Badge>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="secondary" size="sm" prependIcon={<Pencil />} onClick={() => setEditGoalOpen(true)}>
            Edit
          </Button>
          <Button variant="error-outline" size="sm" prependIcon={<Trash2 />} onClick={handleDeleteGoal}>
            Delete
          </Button>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Goal Info */}
        <div className="flex flex-wrap gap-6">
          <Card className="flex-1 min-w-[300px]">
            <h3 className="text-body-sm-medium text-primary mb-2">Description</h3>
            <p className="text-body-sm text-secondary whitespace-pre-wrap">
              {String(goal.description) || "No description provided."}
            </p>
          </Card>

          <Card className="w-64 flex-shrink-0">
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Calendar className="size-4 text-tertiary" />
                <div>
                  <p className="text-caption-sm text-tertiary">Deadline</p>
                  <p className="text-body-sm text-primary">
                    {deadline ? deadline.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" }) : "None set"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Layers className="size-4 text-tertiary" />
                <div>
                  <p className="text-caption-sm text-tertiary">Allocations</p>
                  <p className="text-body-sm text-primary">{String(goal.allocation_count ?? 0)}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Play className="size-4 text-tertiary" />
                <div>
                  <p className="text-caption-sm text-tertiary">Sessions</p>
                  <p className="text-body-sm text-primary">{String(goal.session_count ?? 0)}</p>
                </div>
              </div>
            </div>
          </Card>
        </div>

        {/* KPIs Section */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-body-md-medium text-primary">KPIs ({kpis.length})</h2>
            <Button variant="secondary" size="base" prependIcon={<Plus />} onClick={() => setAddKPIOpen(true)}>
              Add KPI
            </Button>
          </div>

          {kpis.length === 0 ? (
            <Card className="!py-8">
              <div className="text-center">
                <p className="text-body-sm text-tertiary mb-3">No KPIs defined yet. Add one to start tracking metrics.</p>
                <Button variant="primary" prependIcon={<Plus />} onClick={() => setAddKPIOpen(true)}>
                  Add First KPI
                </Button>
              </div>
            </Card>
          ) : (
            <div className="space-y-2">
              {kpis.map((kpi) => {
                const kpiId = String(kpi.id);
                const isExpanded = expandedKPIs.has(kpiId);
                const history = (kpi.history as { date: string; value: number }[]) || [];

                return (
                  <Card key={kpiId} className="!p-0 overflow-hidden">
                    {/* KPI row header */}
                    <div className="flex items-center gap-3 px-4 py-3">
                      <button type="button" onClick={() => toggleKPIExpand(kpiId)} className="text-tertiary hover:text-primary">
                        {isExpanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                      </button>
                      <div className="flex-1 min-w-0">
                        <span className="text-body-sm-medium text-primary">{String(kpi.name)}</span>
                        {kpi.unit ? <span className="text-caption-sm text-tertiary ml-2">({String(kpi.unit)})</span> : null}
                      </div>
                      <div className="text-right mr-4">
                        <span className="text-body-md-medium text-primary">
                          {kpi.current_value !== null ? String(kpi.current_value) : "—"}
                        </span>
                      </div>
                      <Badge variant="neutral" size="sm">{history.length} pts</Badge>
                      <Button variant="ghost" size="sm" prependIcon={<Pencil />} onClick={() => setEditKPI(kpi)}>
                        Edit
                      </Button>
                      {deleteConfirm === kpiId ? (
                        <div className="flex items-center gap-1">
                          <Button variant="error-fill" size="sm" onClick={() => handleDeleteKPI(kpiId)}>
                            Confirm
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => setDeleteConfirm(null)}>
                            Cancel
                          </Button>
                        </div>
                      ) : (
                        <Button variant="ghost" size="sm" prependIcon={<Trash2 />} onClick={() => setDeleteConfirm(kpiId)} className="text-tertiary" />
                      )}
                    </div>

                    {/* Expanded: history chart */}
                    {isExpanded && (
                      <div className="border-t border-subtle px-4 py-3 bg-layer-1">
                        <KPIHistoryChart history={history} unit={String(kpi.unit ?? "")} />
                        {kpi.last_collected ? (
                          <p className="text-caption-sm text-tertiary mt-2">
                            Last collected: {new Date(String(kpi.last_collected)).toLocaleString()}
                          </p>
                        ) : null}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </div>

        {/* Recent Sessions */}
        {sessions.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-body-md-medium text-primary">Recent Sessions ({String(goal.session_count ?? 0)})</h2>
              <Link href={`/${workspaceSlug}/sessions`}>
                <Button variant="ghost" size="sm">View All</Button>
              </Link>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Session</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>Tokens</TableHead>
                  <TableHead>Started</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessions.map((s) => (
                  <TableRow key={String(s.id)}>
                    <TableCell>
                      <Link
                        href={`/${workspaceSlug}/sessions/${String(s.id)}`}
                        className="text-body-sm-medium text-link-primary hover:underline font-mono"
                      >
                        {String(s.acpx_session_id || String(s.id).slice(0, 8))}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Badge variant={String(s.status) === "completed" ? "success" : String(s.status) === "failed" ? "danger" : "neutral"} size="sm">
                        {String(s.status)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-body-sm text-secondary">{String(s.agent_name ?? "—")}</TableCell>
                    <TableCell className="text-body-sm text-secondary font-mono">{Number(s.total_tokens ?? 0).toLocaleString()}</TableCell>
                    <TableCell className="text-caption-sm text-tertiary">
                      {s.started_at ? new Date(String(s.started_at)).toLocaleString() : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Modals */}
      <GoalFormModal
        isOpen={editGoalOpen}
        onClose={() => setEditGoalOpen(false)}
        onSubmit={handleUpdateGoal}
        initialData={{
          name: String(goal.name ?? ""),
          description: String(goal.description ?? ""),
          status: String(goal.status ?? "active"),
          deadline: goal.deadline ? String(goal.deadline) : "",
        }}
        mode="edit"
      />

      <KPIFormModal
        isOpen={addKPIOpen}
        onClose={() => setAddKPIOpen(false)}
        onSubmit={handleCreateKPI}
        mode="create"
      />

      <KPIFormModal
        isOpen={!!editKPI}
        onClose={() => setEditKPI(null)}
        onSubmit={handleUpdateKPI}
        initialData={editKPI ? {
          name: String(editKPI.name ?? ""),
          unit: String(editKPI.unit ?? ""),
          current_value: editKPI.current_value != null ? String(editKPI.current_value) : "",
        } : undefined}
        mode="edit"
      />
    </div>
  );
}
