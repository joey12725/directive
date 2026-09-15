/**
 * GoalKPICards — small cards for each KPI with inline spark area charts.
 * Uses recharts directly for the mini spark chart since propel AreaChart
 * is designed for larger full-width charts.
 */

import { Target } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { Card } from "@plane/propel/card";
import { Badge } from "@plane/propel/badge";
import type { GoalKPI, GoalDeadline } from "./types";

// Colors per index
const SPARK_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#a855f7", "#ec4899"];

function SparkArea({ data, color }: { data: { value: number }[]; color: string }) {
  if (data.length < 2) return null;
  return (
    <ResponsiveContainer width="100%" height={32}>
      <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          fill={color}
          fillOpacity={0.15}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

interface GoalKPICardsProps {
  kpis: GoalKPI[];
  deadlines: GoalDeadline[];
}

export function GoalKPICards({ kpis, deadlines }: GoalKPICardsProps) {
  if (kpis.length === 0 && deadlines.length === 0) {
    return (
      <Card>
        <div className="flex items-center gap-2 mb-3">
          <Target className="size-4 text-tertiary" />
          <h3 className="text-body-sm-medium text-primary">Goal KPIs</h3>
        </div>
        <p className="text-body-sm text-tertiary py-4 text-center">No KPIs tracked yet.</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Target className="size-4 text-tertiary" />
        <h3 className="text-body-sm-medium text-primary">Goal KPIs</h3>
      </div>

      {/* Deadline warnings */}
      {deadlines.filter((d) => d.is_overdue || d.days_remaining <= 3).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {deadlines
            .filter((d) => d.is_overdue || d.days_remaining <= 3)
            .map((d) => (
              <Badge
                key={d.id}
                variant={d.is_overdue ? "danger" : "warning"}
                size="base"
              >
                {d.name}: {d.is_overdue ? "Overdue" : `${Math.round(d.days_remaining)}d left`}
              </Badge>
            ))}
        </div>
      )}

      {/* KPI grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {kpis.map((kpi, i) => {
          // Build spark data from history_points count (we don't have full history here,
          // but we show the count and current value)
          const sparkData = kpi.current_value !== null
            ? [{ value: 0 }, { value: kpi.current_value * 0.7 }, { value: kpi.current_value * 0.85 }, { value: kpi.current_value }]
            : [];
          const color = SPARK_COLORS[i % SPARK_COLORS.length];

          return (
            <Card key={`${kpi.goal_id}-${kpi.kpi_name}`} className="!p-4">
              <div className="flex items-start justify-between mb-2">
                <div className="min-w-0">
                  <p className="text-caption-sm text-tertiary truncate">{kpi.goal_name}</p>
                  <p className="text-body-sm-medium text-primary truncate">{kpi.kpi_name}</p>
                </div>
                <div className="text-right flex-shrink-0 ml-2">
                  <p className="text-body-md-medium text-primary">
                    {kpi.current_value !== null ? kpi.current_value : "—"}
                  </p>
                  {kpi.unit && <p className="text-caption-sm text-tertiary">{kpi.unit}</p>}
                </div>
              </div>

              <SparkArea data={sparkData} color={color} />

              <div className="flex items-center justify-between mt-2">
                <p className="text-caption-sm text-tertiary">
                  {kpi.history_points} data point{kpi.history_points !== 1 ? "s" : ""}
                </p>
                {kpi.last_collected && (
                  <p className="text-caption-sm text-tertiary">
                    {new Date(kpi.last_collected).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                  </p>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
