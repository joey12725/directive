/**
 * CostTracker — area chart showing cost incurred over time by pool.
 * Uses @plane/propel AreaChart (which wraps recharts).
 */

import { useMemo } from "react";
import Link from "next/link";
import { DollarSign, ArrowUpRight } from "lucide-react";
import { Card } from "@plane/propel/card";
import { AreaChart } from "@plane/propel/charts/area-chart";
import type { CostIncurredRow } from "./types";

// Chart colors per pool (rotate through)
const POOL_COLORS = [
  { fill: "rgba(99, 102, 241, 0.15)", stroke: "#6366f1" },   // indigo
  { fill: "rgba(16, 185, 129, 0.15)", stroke: "#10b981" },    // emerald
  { fill: "rgba(245, 158, 11, 0.15)", stroke: "#f59e0b" },    // amber
  { fill: "rgba(239, 68, 68, 0.15)", stroke: "#ef4444" },     // red
  { fill: "rgba(168, 85, 247, 0.15)", stroke: "#a855f7" },    // purple
];

interface CostTrackerProps {
  data: CostIncurredRow[];
  workspaceSlug: string;
}

export function CostTracker({ data, workspaceSlug }: CostTrackerProps) {
  // Pivot pool-per-row data into date-keyed rows with pool columns
  const { chartData, poolNames } = useMemo(() => {
    const dateMap = new Map<string, Record<string, number>>();
    const pools = new Set<string>();

    for (const row of data) {
      pools.add(row.pool);
      if (!dateMap.has(row.date)) dateMap.set(row.date, {});
      const entry = dateMap.get(row.date)!;
      entry[row.pool] = (entry[row.pool] || 0) + row.cost_usd;
    }

    const poolNames = Array.from(pools);
    const chartData = Array.from(dateMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, costs]) => ({
        date,
        ...Object.fromEntries(poolNames.map((p) => [p, costs[p] || 0])),
      }));

    return { chartData, poolNames };
  }, [data]);

  const areas = poolNames.map((pool, i) => {
    const colors = POOL_COLORS[i % POOL_COLORS.length];
    return {
      key: pool,
      label: pool,
      stackId: "cost",
      fill: colors.fill,
      fillOpacity: 0.6,
      showDot: false,
      smoothCurves: true,
      strokeColor: colors.stroke,
      strokeOpacity: 1,
    };
  });

  return (
    <Card>
      <div className="flex items-center gap-2 mb-4">
        <Link href={`/${workspaceSlug}/pools`} className="flex items-center gap-2 group">
          <DollarSign className="size-4 text-tertiary" />
          <h3 className="text-body-sm-medium text-primary group-hover:text-link-primary transition-colors">Cost Over Time</h3>
          <ArrowUpRight className="size-3.5 text-tertiary opacity-0 group-hover:opacity-100 transition-opacity" />
        </Link>
      </div>

      {chartData.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <p className="text-body-sm text-tertiary">No cost data available for this period.</p>
        </div>
      ) : (
        <AreaChart
          className="h-64"
          data={chartData}
          areas={areas}
          xAxis={{ key: "date", label: "Date" }}
          yAxis={{ key: poolNames[0] || "cost", label: "Cost (USD)" }}
          margin={{ top: 5, right: 10, bottom: 5, left: 10 }}
        />
      )}
    </Card>
  );
}
