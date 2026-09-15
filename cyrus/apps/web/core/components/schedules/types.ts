/**
 * Types for the Schedule Editor.
 * Maps to the Django ScheduleRow model.
 */

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
export type Weekday = (typeof WEEKDAYS)[number];

/** Short labels for the toggle buttons */
export const WEEKDAY_LABELS: Record<Weekday, string> = {
  Mon: "M",
  Tue: "T",
  Wed: "W",
  Thu: "T",
  Fri: "F",
  Sat: "S",
  Sun: "S",
};

export interface ScheduleRowData {
  /** Client-side ID for React keys (not persisted) */
  _key: string;
  /** Backend ID if already saved */
  id?: string;
  start_time: string; // "HH:MM" format
  end_time: string;   // "HH:MM" format
  days: Weekday[];
  utilization_pct: number; // 0-100
  priority_modifier: number; // -5 to +5
}

export interface OverlapWarning {
  rowIndices: [number, number];
  day: Weekday;
  overlapStart: string;
  overlapEnd: string;
  combinedUtilization: number;
}

export function createDefaultRow(): ScheduleRowData {
  return {
    _key: crypto.randomUUID(),
    start_time: "09:00",
    end_time: "17:00",
    days: ["Mon", "Tue", "Wed", "Thu", "Fri"],
    utilization_pct: 50,
    priority_modifier: 0,
  };
}
