/**
 * ActivitySummaryCard — session stats with time-window toggle.
 */

import { useState } from "react";
import Link from "next/link";
import { Activity, TrendingUp, Clock, CheckCircle2, ArrowUpRight } from "lucide-react";
import { Card } from "@plane/propel/card";
import type { SessionStats } from "./types";

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  return mins < 60 ? `${mins}m ${Math.round(seconds % 60)}s` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

interface ActivitySummaryCardProps {
  stats: SessionStats;
  workspaceSlug: string;
  /** Called when user changes the time window; parent should re-fetch. */
  onTimeWindowChange?: (days: number) => void;
}

const TIME_WINDOWS = [
  { label: "24h", days: 1 },
  { label: "48h", days: 2 },
  { label: "7d", days: 7 },
] as const;

export function ActivitySummaryCard({ stats, workspaceSlug, onTimeWindowChange }: ActivitySummaryCardProps) {
  const [activeWindow, setActiveWindow] = useState(7);

  const handleChange = (days: number) => {
    setActiveWindow(days);
    onTimeWindowChange?.(days);
  };

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <Link href={`/${workspaceSlug}/sessions`} className="flex items-center gap-2 group">
          <Activity className="size-4 text-tertiary" />
          <h3 className="text-body-sm-medium text-primary group-hover:text-link-primary transition-colors">Session Activity</h3>
          <ArrowUpRight className="size-3.5 text-tertiary opacity-0 group-hover:opacity-100 transition-opacity" />
        </Link>

        {/* Time window tabs */}
        <div className="flex rounded-md border border-subtle overflow-hidden">
          {TIME_WINDOWS.map((tw) => (
            <button
              key={tw.days}
              type="button"
              onClick={() => handleChange(tw.days)}
              className={`px-3 py-1 text-caption-sm-medium transition-colors ${
                activeWindow === tw.days
                  ? "bg-accent-primary text-on-color"
                  : "bg-surface-1 text-tertiary hover:bg-layer-2"
              }`}
            >
              {tw.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-4">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-layer-2 p-2">
            <TrendingUp className="size-4 text-accent-primary" />
          </div>
          <div>
            <p className="text-body-lg-medium text-primary">{stats.total_sessions}</p>
            <p className="text-caption-sm text-tertiary">Total Sessions</p>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="rounded-md bg-layer-2 p-2">
            <CheckCircle2 className="size-4 text-success-primary" />
          </div>
          <div>
            <p className="text-body-lg-medium text-primary">{stats.success_rate_pct}%</p>
            <p className="text-caption-sm text-tertiary">Success Rate</p>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="rounded-md bg-layer-2 p-2">
            <Clock className="size-4 text-tertiary" />
          </div>
          <div>
            <p className="text-body-lg-medium text-primary">{formatDuration(stats.avg_duration_seconds)}</p>
            <p className="text-caption-sm text-tertiary">Avg Duration</p>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="rounded-md bg-layer-2 p-2">
            <Activity className="size-4 text-brand-primary" />
          </div>
          <div>
            <p className="text-body-lg-medium text-primary">{stats.completed_sessions}</p>
            <p className="text-caption-sm text-tertiary">Completed</p>
          </div>
        </div>
      </div>
    </Card>
  );
}
