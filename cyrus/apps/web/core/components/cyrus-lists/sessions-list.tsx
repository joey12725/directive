/**
 * Sessions list view — /sessions
 */

import { Play } from "lucide-react";
import Link from "next/link";
import { useParams } from "react-router";
import useSWR from "swr";
import { Badge } from "@plane/propel/badge";
import { Skeleton } from "@plane/propel/skeleton";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@plane/propel/table";
import { cyrusCrudService } from "@/services/cyrus-crud.service";

const STATUS_VARIANT: Record<string, "success" | "danger" | "warning" | "neutral" | "brand"> = {
  running: "brand",
  completed: "success",
  failed: "danger",
  cancelled: "neutral",
  rate_limited: "warning",
};

interface SessionsListProps {
  workspaceSlug: string;
}

export function SessionsList({ workspaceSlug }: SessionsListProps) {
  const { data, isLoading } = useSWR(
    `CYRUS_SESSIONS_LIST_${workspaceSlug}`,
    () => cyrusCrudService.listSessions(workspaceSlug)
  );

  const sessions = data?.results ?? [];

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="flex items-center gap-2 mb-6">
        <Play className="size-5 text-tertiary" />
        <h1 className="text-body-xl-medium text-primary">Sessions</h1>
        <span className="text-caption-sm text-tertiary">({sessions.length})</span>
      </div>

      {isLoading ? (
        <Skeleton>
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton.Item key={i} height="48px" width="100%" className="mt-2" />
          ))}
        </Skeleton>
      ) : sessions.length === 0 ? (
        <div className="text-center py-16">
          <Play className="size-8 text-tertiary mx-auto mb-3" />
          <p className="text-body-sm text-tertiary">No sessions recorded yet.</p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Session</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Agent</TableHead>
              <TableHead>Tokens</TableHead>
              <TableHead>Cost</TableHead>
              <TableHead>Started</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sessions.map((s: Record<string, unknown>) => (
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
                  <Badge variant={STATUS_VARIANT[String(s.status)] ?? "neutral"} size="base">
                    {String(s.status ?? "unknown")}
                  </Badge>
                </TableCell>
                <TableCell className="text-body-sm text-secondary">
                  {String(s.agent_name ?? s.agent ?? "—")}
                </TableCell>
                <TableCell className="text-body-sm text-secondary font-mono">
                  {Number(s.total_tokens ?? 0).toLocaleString()}
                </TableCell>
                <TableCell className="text-body-sm text-secondary font-mono">
                  ${Number(s.estimated_cost_usd ?? 0).toFixed(4)}
                </TableCell>
                <TableCell className="text-caption-sm text-tertiary">
                  {s.started_at ? new Date(String(s.started_at)).toLocaleString() : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
