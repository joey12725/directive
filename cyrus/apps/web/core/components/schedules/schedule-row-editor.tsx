/**
 * Single schedule row editor.
 * Renders time pickers, weekday toggles, utilization slider, priority modifier, and remove button.
 */

import { Trash2 } from "lucide-react";
import { Button } from "@plane/propel/button";
import { WEEKDAYS, WEEKDAY_LABELS } from "./types";
import type { ScheduleRowData, Weekday } from "./types";

interface ScheduleRowEditorProps {
  row: ScheduleRowData;
  index: number;
  onChange: (index: number, updated: ScheduleRowData) => void;
  onRemove: (index: number) => void;
  hasWarning: boolean;
}

export function ScheduleRowEditor({ row, index, onChange, onRemove, hasWarning }: ScheduleRowEditorProps) {
  const update = (patch: Partial<ScheduleRowData>) => {
    onChange(index, { ...row, ...patch });
  };

  const toggleDay = (day: Weekday) => {
    const next = row.days.includes(day) ? row.days.filter((d) => d !== day) : [...row.days, day];
    update({ days: next });
  };

  return (
    <div
      className={`rounded-lg border p-4 space-y-4 transition-colors ${
        hasWarning
          ? "border-warning-primary bg-warning-subtle/30"
          : "border-subtle bg-surface-1"
      }`}
    >
      {/* Row header */}
      <div className="flex items-center justify-between">
        <span className="text-body-sm-medium text-primary">Time Block {index + 1}</span>
        <Button
          variant="ghost"
          size="sm"
          prependIcon={<Trash2 />}
          onClick={() => onRemove(index)}
          className="text-tertiary hover:text-danger-primary"
        >
          Remove
        </Button>
      </div>

      {/* Time pickers row */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label className="text-caption-sm text-tertiary whitespace-nowrap" htmlFor={`start-${row._key}`}>
            Start
          </label>
          <input
            id={`start-${row._key}`}
            type="time"
            value={row.start_time}
            onChange={(e) => update({ start_time: e.target.value })}
            className="rounded-md border border-subtle bg-surface-1 px-2 py-1.5 text-body-sm text-primary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
          />
        </div>
        <span className="text-caption-sm text-tertiary">to</span>
        <div className="flex items-center gap-2">
          <label className="text-caption-sm text-tertiary whitespace-nowrap" htmlFor={`end-${row._key}`}>
            End
          </label>
          <input
            id={`end-${row._key}`}
            type="time"
            value={row.end_time}
            onChange={(e) => update({ end_time: e.target.value })}
            className="rounded-md border border-subtle bg-surface-1 px-2 py-1.5 text-body-sm text-primary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
          />
        </div>
      </div>

      {/* Weekday toggles */}
      <div>
        <p className="text-caption-sm text-tertiary mb-2">Active Days</p>
        <div className="flex gap-1.5">
          {WEEKDAYS.map((day) => {
            const isActive = row.days.includes(day);
            return (
              <button
                key={day}
                type="button"
                onClick={() => toggleDay(day)}
                title={day}
                className={`size-8 rounded-md text-caption-md-medium transition-colors focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-1 ${
                  isActive
                    ? "bg-accent-primary text-on-color"
                    : "bg-layer-2 text-tertiary hover:bg-layer-3 hover:text-secondary"
                }`}
              >
                {WEEKDAY_LABELS[day]}
              </button>
            );
          })}
        </div>
      </div>

      {/* Utilization + Priority row */}
      <div className="flex flex-wrap gap-6">
        {/* Utilization slider */}
        <div className="flex-1 min-w-[200px]">
          <div className="flex items-center justify-between mb-2">
            <label className="text-caption-sm text-tertiary" htmlFor={`util-${row._key}`}>
              Utilization
            </label>
            <span className="text-caption-md-medium text-primary">{row.utilization_pct}%</span>
          </div>
          <input
            id={`util-${row._key}`}
            type="range"
            min={0}
            max={100}
            step={5}
            value={row.utilization_pct}
            onChange={(e) => update({ utilization_pct: Number(e.target.value) })}
            className="w-full h-1.5 rounded-full appearance-none bg-layer-3 accent-accent-primary cursor-pointer"
          />
          <div className="flex justify-between text-caption-sm text-tertiary mt-1">
            <span>0%</span>
            <span>50%</span>
            <span>100%</span>
          </div>
        </div>

        {/* Priority modifier */}
        <div className="w-32">
          <div className="flex items-center justify-between mb-2">
            <label className="text-caption-sm text-tertiary" htmlFor={`prio-${row._key}`}>
              Priority
            </label>
            <span className="text-caption-md-medium text-primary">
              {row.priority_modifier > 0 ? "+" : ""}
              {row.priority_modifier}
            </span>
          </div>
          <input
            id={`prio-${row._key}`}
            type="range"
            min={-5}
            max={5}
            step={1}
            value={row.priority_modifier}
            onChange={(e) => update({ priority_modifier: Number(e.target.value) })}
            className="w-full h-1.5 rounded-full appearance-none bg-layer-3 accent-accent-primary cursor-pointer"
          />
          <div className="flex justify-between text-caption-sm text-tertiary mt-1">
            <span>-5</span>
            <span>0</span>
            <span>+5</span>
          </div>
        </div>
      </div>
    </div>
  );
}
