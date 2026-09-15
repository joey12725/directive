/**
 * KPI history chart — renders the history JSON array as an area chart.
 */

import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis, Tooltip } from "recharts";

interface HistoryPoint {
  date: string;
  value: number;
}

interface KPIHistoryChartProps {
  history: HistoryPoint[];
  unit: string;
  color?: string;
}

export function KPIHistoryChart({ history, unit, color = "#6366f1" }: KPIHistoryChartProps) {
  if (!history || history.length < 2) {
    return (
      <p className="text-caption-sm text-tertiary py-4 text-center">
        Not enough data points for a chart (need at least 2).
      </p>
    );
  }

  return (
    <div className="h-40">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={history} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "var(--text-color-tertiary)" }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--text-color-tertiary)" }}
            tickLine={false}
            axisLine={false}
            width={40}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--bg-surface-1)",
              border: "1px solid var(--border-color-subtle)",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value: number) => [`${value} ${unit}`, "Value"]}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            fill={color}
            fillOpacity={0.1}
            strokeWidth={2}
            dot={{ fill: color, r: 3 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
