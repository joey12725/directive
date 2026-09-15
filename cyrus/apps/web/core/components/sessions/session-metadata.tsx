/**
 * Session metadata sidebar card.
 * Shows agent, goal, project, work item, duration, tokens, cost, and Langfuse link.
 */

import {
  Bot,
  Target,
  FolderKanban,
  FileText,
  Clock,
  Coins,
  Zap,
  ExternalLink,
  ArrowUpRight,
} from "lucide-react";
import { Badge } from "@plane/propel/badge";
import { Button } from "@plane/propel/button";
import { Card } from "@plane/propel/card";
import type { Session, SessionStatus } from "./types";

const STATUS_CONFIG: Record<SessionStatus, { label: string; variant: "success" | "danger" | "warning" | "neutral" | "brand" }> = {
  running: { label: "Running", variant: "brand" },
  completed: { label: "Completed", variant: "success" },
  failed: { label: "Failed", variant: "danger" },
  cancelled: { label: "Cancelled", variant: "neutral" },
  rate_limited: { label: "Rate Limited", variant: "warning" },
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins < 60) return `${mins}m ${secs}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatCost(usd: string | number): string {
  const val = typeof usd === "string" ? parseFloat(usd) : usd;
  if (isNaN(val)) return "$0.00";
  if (val < 0.01) return `$${val.toFixed(6)}`;
  return `$${val.toFixed(4)}`;
}

function MetaRow({ icon: Icon, label, children }: { icon: React.ElementType; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-2">
      <Icon className="size-4 text-tertiary mt-0.5 flex-shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-caption-sm text-tertiary">{label}</p>
        <div className="text-body-sm text-primary mt-0.5 break-words">{children}</div>
      </div>
    </div>
  );
}

interface SessionMetadataProps {
  session: Session;
  workspaceSlug: string;
}

export function SessionMetadata({ session, workspaceSlug }: SessionMetadataProps) {
  const statusConfig = STATUS_CONFIG[session.status] || STATUS_CONFIG.cancelled;
  const startDate = new Date(session.started_at);

  return (
    <Card className="sticky top-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-body-md-medium text-primary">Session Details</h3>
        <Badge variant={statusConfig.variant} size="base">
          {statusConfig.label}
        </Badge>
      </div>

      <p className="text-caption-sm text-tertiary mt-1">
        {startDate.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
        {" at "}
        {startDate.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
      </p>

      {/* Divider */}
      <div className="border-t border-subtle my-3" />

      {/* Metadata rows */}
      <div className="space-y-1">
        {session.agent_name && (
          <MetaRow icon={Bot} label="Agent">
            <span className="font-mono text-caption-md">{session.agent_name}</span>
          </MetaRow>
        )}

        {session.model_name && (
          <MetaRow icon={Zap} label="Model">
            <span className="font-mono text-caption-md">{session.model_name}</span>
          </MetaRow>
        )}

        {session.goal_name && (
          <MetaRow icon={Target} label="Goal">
            {session.goal_name}
          </MetaRow>
        )}

        {session.project_name && (
          <MetaRow icon={FolderKanban} label="Project">
            {session.project_name}
          </MetaRow>
        )}

        {session.work_item_name && (
          <MetaRow icon={FileText} label="Work Item">
            {session.project && session.work_item ? (
              <a
                href={`/${workspaceSlug}/projects/${session.project}/issues/${session.work_item}`}
                className="text-link-primary hover:underline inline-flex items-center gap-1"
              >
                {session.work_item_name}
                <ArrowUpRight className="size-3" />
              </a>
            ) : (
              session.work_item_name
            )}
          </MetaRow>
        )}

        <MetaRow icon={Clock} label="Duration">
          {formatDuration(session.duration_seconds)}
        </MetaRow>
      </div>

      {/* Divider */}
      <div className="border-t border-subtle my-3" />

      {/* Token & Cost stats */}
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-layer-2 px-3 py-2 text-center">
          <p className="text-caption-sm text-tertiary">Input</p>
          <p className="text-body-sm-medium text-primary">{formatTokens(session.input_tokens)}</p>
        </div>
        <div className="rounded-lg bg-layer-2 px-3 py-2 text-center">
          <p className="text-caption-sm text-tertiary">Output</p>
          <p className="text-body-sm-medium text-primary">{formatTokens(session.output_tokens)}</p>
        </div>
        <div className="rounded-lg bg-layer-2 px-3 py-2 text-center">
          <p className="text-caption-sm text-tertiary">Total Tokens</p>
          <p className="text-body-sm-medium text-primary">{formatTokens(session.total_tokens)}</p>
        </div>
        <div className="rounded-lg bg-layer-2 px-3 py-2 text-center">
          <p className="text-caption-sm text-tertiary">Cost</p>
          <p className="text-body-sm-medium text-primary">{formatCost(session.estimated_cost_usd)}</p>
        </div>
      </div>

      {/* Rate limit warning */}
      {session.was_rate_limited && (
        <div className="mt-3 rounded-lg bg-warning-subtle px-3 py-2">
          <p className="text-caption-sm text-warning-primary">
            Rate limited — waited {Math.round(session.rate_limit_wait_seconds)}s
          </p>
        </div>
      )}

      {/* Langfuse trace link */}
      {session.langfuse_trace_url && (
        <div className="mt-3">
          <Button
            variant="secondary"
            size="lg"
            className="w-full"
            appendIcon={<ExternalLink />}
            onClick={() => window.open(session.langfuse_trace_url, "_blank", "noopener")}
          >
            View Langfuse Trace
          </Button>
        </div>
      )}

      {/* Summary */}
      {session.summary && (
        <>
          <div className="border-t border-subtle my-3" />
          <div>
            <p className="text-caption-sm-medium text-tertiary mb-1">Summary</p>
            <p className="text-body-sm text-secondary whitespace-pre-wrap">{session.summary}</p>
          </div>
        </>
      )}
    </Card>
  );
}
