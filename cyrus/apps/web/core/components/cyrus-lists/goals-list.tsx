/**
 * Goals list view — /goals
 * Full CRUD: create, click-to-detail, status filter, KPI count.
 */

import { useState } from "react";
import Link from "next/link";
import { Target, Plus } from "lucide-react";
import useSWR, { useSWRConfig } from "swr";
import { Badge } from "@plane/propel/badge";
import { Button } from "@plane/propel/button";
import { Skeleton } from "@plane/propel/skeleton";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@plane/propel/table";
import { cyrusCrudService } from "@/services/cyrus-crud.service";
import { GoalFormModal } from "@/components/goals/goal-form-modal";

const STATUS_VARIANT: Record<string, "success" | "warning" | "neutral"> = {
  active: "success",
  paused: "warning",
  archived: "neutral",
};

const STATUS_FILTERS = [
  { label: "All", value: "" },
  { label: "Active", value: "active" },
  { label: "Paused", value: "paused" },
  { label: "Archived", value: "archived" },
] as const;

interface GoalsListProps {
  workspaceSlug: string;
}

export function GoalsList({ workspaceSlug }: GoalsListProps) {
  const [statusFilter, setStatusFilter] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const { mutate } = useSWRConfig();

  const cacheKey = `CYRUS_GOALS_LIST_${workspaceSlug}${statusFilter ? `_${statusFilter}` : ""}`;
  const { data, isLoading } = useSWR(cacheKey, () =>
    cyrusCrudService.listGoals(workspaceSlug, statusFilter || undefined)
  );

  const goals = data?.results ?? [];

  const handleCreate = async (formData: Record<string, unknown>) => {
    await cyrusCrudService.createGoal(workspaceSlug, formData);
    mutate(cacheKey);
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <Target className="size-5 text-tertiary" />
          <h1 className="text-body-xl-medium text-primary">Goals</h1>
          <span className="text-caption-sm text-tertiary">({goals.length})</span>
        </div>
        <Button variant="primary" size="base" prependIcon={<Plus />} onClick={() => setCreateOpen(true)}>
          Create Goal
        </Button>
      </div>

      {/* Status filter tabs */}
      <div className="flex rounded-md border border-subtle overflow-hidden mb-4 w-fit">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            onClick={() => setStatusFilter(f.value)}
            className={`px-3 py-1.5 text-caption-sm-medium transition-colors ${
              statusFilter === f.value
                ? "bg-accent-primary text-on-color"
                : "bg-surface-1 text-tertiary hover:bg-layer-2"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Table */}
      {isLoading ? (
        <Skeleton>
          {[1, 2, 3, 4].map((i) => (
            <Skeleton.Item key={i} height="48px" width="100%" className="mt-2" />
          ))}
        </Skeleton>
      ) : goals.length === 0 ? (
        <div className="text-center py-16">
          <Target className="size-8 text-tertiary mx-auto mb-3" />
          <p className="text-body-sm text-tertiary mb-4">
            {statusFilter ? `No ${statusFilter} goals found.` : "No goals configured yet."}
          </p>
          {!statusFilter && (
            <Button variant="primary" prependIcon={<Plus />} onClick={() => setCreateOpen(true)}>
              Create First Goal
            </Button>
          )}
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Deadline</TableHead>
              <TableHead>KPIs</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {goals.map((g: Record<string, unknown>) => (
              <TableRow key={String(g.id)} className="cursor-pointer hover:bg-layer-1">
                <TableCell>
                  <Link
                    href={`/${workspaceSlug}/goals/${String(g.id)}`}
                    className="text-body-sm-medium text-link-primary hover:underline"
                  >
                    {String(g.name ?? "—")}
                  </Link>
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[String(g.status)] ?? "neutral"} size="base">
                    {String(g.status ?? "unknown")}
                  </Badge>
                </TableCell>
                <TableCell className="text-body-sm text-secondary">
                  {g.deadline ? new Date(String(g.deadline)).toLocaleDateString() : "—"}
                </TableCell>
                <TableCell className="text-body-sm text-secondary">
                  {g.kpi_count != null ? String(g.kpi_count) : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {/* Create modal */}
      <GoalFormModal
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate}
        mode="create"
      />
    </div>
  );
}
