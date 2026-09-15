/**
 * Agents list view — /agents
 */

import { Bot } from "lucide-react";
import useSWR from "swr";
import { Badge } from "@plane/propel/badge";
import { Skeleton } from "@plane/propel/skeleton";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@plane/propel/table";
import { cyrusCrudService } from "@/services/cyrus-crud.service";

const STATUS_VARIANT: Record<string, "success" | "danger" | "warning" | "neutral"> = {
  online: "success",
  offline: "neutral",
  degraded: "warning",
  errored: "danger",
};

interface AgentsListProps {
  workspaceSlug: string;
}

export function AgentsList({ workspaceSlug }: AgentsListProps) {
  const { data, isLoading } = useSWR(
    `CYRUS_AGENTS_LIST_${workspaceSlug}`,
    () => cyrusCrudService.listAgents(workspaceSlug)
  );

  const agents = data?.results ?? [];

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="flex items-center gap-2 mb-6">
        <Bot className="size-5 text-tertiary" />
        <h1 className="text-body-xl-medium text-primary">Agents</h1>
        <span className="text-caption-sm text-tertiary">({agents.length})</span>
      </div>

      {isLoading ? (
        <Skeleton>
          {[1, 2, 3, 4].map((i) => (
            <Skeleton.Item key={i} height="48px" width="100%" className="mt-2" />
          ))}
        </Skeleton>
      ) : agents.length === 0 ? (
        <div className="text-center py-16">
          <Bot className="size-8 text-tertiary mx-auto mb-3" />
          <p className="text-body-sm text-tertiary">No agents configured yet.</p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Relay URL</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Pool</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {agents.map((a: Record<string, unknown>) => (
              <TableRow key={String(a.id)}>
                <TableCell className="text-body-sm-medium text-primary">{String(a.name ?? "—")}</TableCell>
                <TableCell>
                  <span className="text-body-sm text-secondary font-mono">{String(a.agent_type ?? "—")}</span>
                </TableCell>
                <TableCell className="text-caption-sm text-tertiary font-mono max-w-[200px] truncate">
                  {String(a.relay_url ?? "—")}
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[String(a.status)] ?? "neutral"} size="base">
                    {String(a.status ?? "unknown")}
                  </Badge>
                </TableCell>
                <TableCell className="text-body-sm text-secondary">{String(a.pool_name ?? a.pool ?? "—")}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
