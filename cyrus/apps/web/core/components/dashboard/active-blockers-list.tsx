/**
 * ActiveBlockersList — shows blockers and pending approvals.
 */

import { AlertTriangle, ShieldCheck, Compass } from "lucide-react";
import { Card } from "@plane/propel/card";
import { Badge } from "@plane/propel/badge";
import type { ActiveAlerts } from "./types";

interface ActiveBlockersListProps {
  alerts: ActiveAlerts;
}

function BlockerRow({
  icon: Icon,
  label,
  count,
  variant,
}: {
  icon: React.ElementType;
  label: string;
  count: number;
  variant: "danger" | "warning" | "neutral";
}) {
  if (count === 0) return null;
  return (
    <div className="flex items-center gap-3 py-2.5">
      <Icon className={`size-4 flex-shrink-0 ${
        variant === "danger" ? "text-danger-primary" : variant === "warning" ? "text-warning-primary" : "text-tertiary"
      }`} />
      <span className="text-body-sm text-primary flex-1">{label}</span>
      <Badge variant={variant} size="base">{count}</Badge>
    </div>
  );
}

export function ActiveBlockersList({ alerts }: ActiveBlockersListProps) {
  const total = alerts.active_blockers + alerts.pending_approvals + alerts.alignment_drift;

  return (
    <Card>
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="size-4 text-tertiary" />
        <h3 className="text-body-sm-medium text-primary">Active Blockers</h3>
        {total > 0 && <Badge variant="danger" size="sm">{total}</Badge>}
      </div>

      {total === 0 ? (
        <p className="text-body-sm text-tertiary py-4 text-center">No active blockers. All clear.</p>
      ) : (
        <div className="divide-y divide-subtle">
          <BlockerRow icon={AlertTriangle} label="Failed / Rate-Limited Sessions" count={alerts.active_blockers} variant="danger" />
          <BlockerRow icon={ShieldCheck} label="Pending Approvals" count={alerts.pending_approvals} variant="warning" />
          <BlockerRow icon={Compass} label="Alignment Drift Flags" count={alerts.alignment_drift} variant="warning" />
        </div>
      )}
    </Card>
  );
}
