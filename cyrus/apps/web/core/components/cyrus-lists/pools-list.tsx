/**
 * Pools list view — /pools
 */

import { Server } from "lucide-react";
import useSWR from "swr";
import { Badge } from "@plane/propel/badge";
import { Skeleton } from "@plane/propel/skeleton";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@plane/propel/table";
import { cyrusCrudService } from "@/services/cyrus-crud.service";

interface PoolsListProps {
  workspaceSlug: string;
}

export function PoolsList({ workspaceSlug }: PoolsListProps) {
  const { data, isLoading } = useSWR(
    `CYRUS_POOLS_LIST_${workspaceSlug}`,
    () => cyrusCrudService.listPools(workspaceSlug)
  );

  const pools = data?.results ?? [];

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="flex items-center gap-2 mb-6">
        <Server className="size-5 text-tertiary" />
        <h1 className="text-body-xl-medium text-primary">Compute Pools</h1>
        <span className="text-caption-sm text-tertiary">({pools.length})</span>
      </div>

      {isLoading ? (
        <Skeleton>
          {[1, 2, 3].map((i) => (
            <Skeleton.Item key={i} height="48px" width="100%" className="mt-2" />
          ))}
        </Skeleton>
      ) : pools.length === 0 ? (
        <div className="text-center py-16">
          <Server className="size-8 text-tertiary mx-auto mb-3" />
          <p className="text-body-sm text-tertiary">No compute pools configured yet.</p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Budget Limit</TableHead>
              <TableHead>Period</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pools.map((p: Record<string, unknown>) => (
              <TableRow key={String(p.id)}>
                <TableCell className="text-body-sm-medium text-primary">{String(p.name ?? "—")}</TableCell>
                <TableCell className="text-body-sm text-secondary capitalize">{String(p.provider ?? "—")}</TableCell>
                <TableCell>
                  <Badge
                    variant={String(p.pool_type) === "subscription" ? "brand" : "neutral"}
                    size="base"
                  >
                    {String(p.pool_type) === "api_billing" ? "API Billing" : "Subscription"}
                  </Badge>
                </TableCell>
                <TableCell className="text-body-sm text-secondary font-mono">
                  ${Number(p.budget_limit_usd ?? 0).toFixed(2)}
                </TableCell>
                <TableCell className="text-body-sm text-tertiary capitalize">
                  {String(p.budget_period ?? "—")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
