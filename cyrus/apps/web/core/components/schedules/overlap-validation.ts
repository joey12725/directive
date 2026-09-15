/**
 * Overlap detection for schedule rows.
 *
 * Two rows overlap on a given day when their time ranges intersect.
 * If the combined utilization_pct of overlapping rows exceeds 100%,
 * a warning is emitted.
 */

import type { ScheduleRowData, Weekday, OverlapWarning } from "./types";

/** Convert "HH:MM" to minutes since midnight. */
function timeToMinutes(t: string): number {
  const [h, m] = t.split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
}

/** Convert minutes since midnight back to "HH:MM". */
function minutesToTime(mins: number): string {
  const h = Math.floor(mins / 60) % 24;
  const m = mins % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/**
 * Detect all pairwise overlaps that exceed 100% combined utilization.
 *
 * Returns an array of warnings. We check every pair of rows; for each
 * shared day, if their time intervals overlap and their utilization
 * sums to > 100%, a warning is produced.
 */
export function detectOverlaps(rows: ScheduleRowData[]): OverlapWarning[] {
  const warnings: OverlapWarning[] = [];

  for (let i = 0; i < rows.length; i++) {
    for (let j = i + 1; j < rows.length; j++) {
      const a = rows[i];
      const b = rows[j];

      // Find shared days
      const sharedDays = a.days.filter((d) => b.days.includes(d));
      if (sharedDays.length === 0) continue;

      const aStart = timeToMinutes(a.start_time);
      const aEnd = timeToMinutes(a.end_time);
      const bStart = timeToMinutes(b.start_time);
      const bEnd = timeToMinutes(b.end_time);

      // Check time overlap (assumes start < end, no midnight wrap)
      const overlapStart = Math.max(aStart, bStart);
      const overlapEnd = Math.min(aEnd, bEnd);

      if (overlapStart >= overlapEnd) continue;

      const combined = a.utilization_pct + b.utilization_pct;
      if (combined <= 100) continue;

      // Emit one warning per shared day
      for (const day of sharedDays) {
        warnings.push({
          rowIndices: [i, j],
          day: day as Weekday,
          overlapStart: minutesToTime(overlapStart),
          overlapEnd: minutesToTime(overlapEnd),
          combinedUtilization: combined,
        });
      }
    }
  }

  return warnings;
}

// Re-export helpers for testing
export { timeToMinutes, minutesToTime };
