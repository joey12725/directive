/**
 * Top strip metric cards: Utilization, Active Agents, Agent Health, Pending Approvals.
 * Each card links to a drill-down page.
 */

import Link from "next/link";
import {
  Bot,
  HeartPulse,
  ShieldAlert,
  CheckCircle2,
  ArrowUpRight,
} from "lucide-react";
import { Card } from "@plane/propel/card";
import { Badge } from "@plane/propel/badge";
import type { ActiveAlerts, AgentHealthRow, PoolBudgetRow } from "./types";

// ---------------------------------------------------------------------------
// Clickable card wrapper
// ---------------------------------------------------------------------------
function LinkedCard({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="block group">
      <Card className="flex !flex-row items-center gap-4 transition-shadow group-hover:shadow-raised-200">
        {children}
        <ArrowUpRight className="size-4 text-tertiary opacity-0 group-hover:opacity-100 transition-opacity ml-auto flex-shrink-0" />
      </Card>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Circular progress SVG
// ---------------------------------------------------------------------------
function CircularProgress({ value, size = 48 }: { value: number; size?: number }) {
  const radius = (size - 6) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(Math.max(value, 0), 100);
  const offset = circumference - (clamped / 100) * circumference;
  const color = clamped > 90 ? "var(--text-color-danger)" : clamped > 70 ? "var(--text-color-warning)" : "var(--text-color-success)";

  return (
    <svg width={size} height={size} className="flex-shrink-0">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--border-color-subtle)" strokeWidth={4} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={4}
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        className="transition-all duration-500"
      />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="text-caption-sm-medium fill-primary">
        {Math.round(clamped)}%
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Individual metric cards
// ---------------------------------------------------------------------------

export function UtilizationCard({ pools, workspaceSlug }: { pools: PoolBudgetRow[]; workspaceSlug: string }) {
  const avgUtil = pools.length > 0
    ? Math.round(pools.reduce((sum, p) => sum + p.utilization_pct, 0) / pools.length)
    : 0;

  return (
    <LinkedCard href={`/${workspaceSlug}/pools`}>
      <CircularProgress value={avgUtil} />
      <div>
        <p className="text-caption-sm text-tertiary">Avg Utilization</p>
        <p className="text-body-lg-medium text-primary">{avgUtil}%</p>
        <p className="text-caption-sm text-tertiary">{pools.length} pool{pools.length !== 1 ? "s" : ""}</p>
      </div>
    </LinkedCard>
  );
}

export function ActiveAgentsCard({ agents, workspaceSlug }: { agents: AgentHealthRow[]; workspaceSlug: string }) {
  const online = agents.filter((a) => a.status === "online").length;

  return (
    <LinkedCard href={`/${workspaceSlug}/agents`}>
      <div className="rounded-lg bg-brand-subtle p-2.5">
        <Bot className="size-5 text-accent-primary" />
      </div>
      <div>
        <p className="text-caption-sm text-tertiary">Active Agents</p>
        <p className="text-body-lg-medium text-primary">
          {online} <span className="text-caption-sm text-tertiary">/ {agents.length}</span>
        </p>
        <p className="text-caption-sm text-tertiary">
          {agents.filter((a) => a.active_sessions > 0).length} running sessions
        </p>
      </div>
    </LinkedCard>
  );
}

export function AgentHealthCard({ agents, workspaceSlug }: { agents: AgentHealthRow[]; workspaceSlug: string }) {
  const degraded = agents.filter((a) => a.status === "degraded").length;
  const errored = agents.filter((a) => a.status === "errored").length;
  const healthy = agents.length - degraded - errored;
  const hasIssues = degraded + errored > 0;

  return (
    <LinkedCard href={`/${workspaceSlug}/agents`}>
      <div className={`rounded-lg p-2.5 ${hasIssues ? "bg-warning-subtle" : "bg-success-subtle-1"}`}>
        <HeartPulse className={`size-5 ${hasIssues ? "text-warning-primary" : "text-success-primary"}`} />
      </div>
      <div>
        <p className="text-caption-sm text-tertiary">Agent Health</p>
        {hasIssues ? (
          <div className="flex items-center gap-2 mt-0.5">
            {errored > 0 && <Badge variant="danger" size="sm">{errored} errored</Badge>}
            {degraded > 0 && <Badge variant="warning" size="sm">{degraded} degraded</Badge>}
          </div>
        ) : (
          <div className="flex items-center gap-1.5 mt-0.5">
            <CheckCircle2 className="size-4 text-success-primary" />
            <span className="text-body-sm-medium text-success-primary">All healthy</span>
          </div>
        )}
        <p className="text-caption-sm text-tertiary mt-0.5">{healthy} online</p>
      </div>
    </LinkedCard>
  );
}

export function PendingApprovalsCard({ alerts, workspaceSlug }: { alerts: ActiveAlerts; workspaceSlug: string }) {
  const total = alerts.pending_approvals + alerts.active_blockers + alerts.alignment_drift;

  return (
    <LinkedCard href={`/${workspaceSlug}/settings/cyrus/approvals`}>
      <div className={`rounded-lg p-2.5 ${total > 0 ? "bg-danger-subtle" : "bg-layer-2"}`}>
        <ShieldAlert className={`size-5 ${total > 0 ? "text-danger-primary" : "text-tertiary"}`} />
      </div>
      <div>
        <p className="text-caption-sm text-tertiary">Pending Actions</p>
        <p className="text-body-lg-medium text-primary">{total}</p>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-caption-sm text-tertiary">
          {alerts.pending_approvals > 0 && <span>{alerts.pending_approvals} approvals</span>}
          {alerts.active_blockers > 0 && <span>{alerts.active_blockers} blockers</span>}
          {alerts.alignment_drift > 0 && <span>{alerts.alignment_drift} drift</span>}
          {total === 0 && <span>No pending actions</span>}
        </div>
      </div>
    </LinkedCard>
  );
}
