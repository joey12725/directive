/**
 * Tests for schedule overlap detection logic.
 * Covers: no overlap, partial overlap, full overlap, multi-day,
 * different days, boundary cases, and >2 row interactions.
 */

import { describe, it, expect } from "vitest";
import { detectOverlaps } from "./overlap-validation";
import { createDefaultRow } from "./types";
import type { ScheduleRowData } from "./types";

function row(overrides: Partial<ScheduleRowData> = {}): ScheduleRowData {
  return { ...createDefaultRow(), ...overrides };
}

describe("detectOverlaps", () => {
  it("returns empty for no rows", () => {
    expect(detectOverlaps([])).toEqual([]);
  });

  it("returns empty for a single row", () => {
    expect(detectOverlaps([row()])).toEqual([]);
  });

  it("returns empty when rows have no overlapping days", () => {
    const rows = [
      row({ days: ["Mon", "Tue"], start_time: "09:00", end_time: "17:00", utilization_pct: 80 }),
      row({ days: ["Wed", "Thu"], start_time: "09:00", end_time: "17:00", utilization_pct: 80 }),
    ];
    expect(detectOverlaps(rows)).toEqual([]);
  });

  it("returns empty when time ranges do not overlap", () => {
    const rows = [
      row({ days: ["Mon"], start_time: "09:00", end_time: "12:00", utilization_pct: 80 }),
      row({ days: ["Mon"], start_time: "13:00", end_time: "17:00", utilization_pct: 80 }),
    ];
    expect(detectOverlaps(rows)).toEqual([]);
  });

  it("returns empty when overlapping rows sum to <= 100%", () => {
    const rows = [
      row({ days: ["Mon"], start_time: "09:00", end_time: "17:00", utilization_pct: 50 }),
      row({ days: ["Mon"], start_time: "09:00", end_time: "17:00", utilization_pct: 50 }),
    ];
    expect(detectOverlaps(rows)).toEqual([]);
  });

  it("detects overlap when combined utilization > 100%", () => {
    const rows = [
      row({ days: ["Mon"], start_time: "09:00", end_time: "17:00", utilization_pct: 60 }),
      row({ days: ["Mon"], start_time: "09:00", end_time: "17:00", utilization_pct: 60 }),
    ];
    const warnings = detectOverlaps(rows);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toMatchObject({
      rowIndices: [0, 1],
      day: "Mon",
      overlapStart: "09:00",
      overlapEnd: "17:00",
      combinedUtilization: 120,
    });
  });

  it("detects partial time overlap", () => {
    const rows = [
      row({ days: ["Mon"], start_time: "09:00", end_time: "14:00", utilization_pct: 80 }),
      row({ days: ["Mon"], start_time: "12:00", end_time: "17:00", utilization_pct: 80 }),
    ];
    const warnings = detectOverlaps(rows);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toMatchObject({
      overlapStart: "12:00",
      overlapEnd: "14:00",
      combinedUtilization: 160,
    });
  });

  it("emits warnings for each shared day", () => {
    const rows = [
      row({ days: ["Mon", "Tue", "Wed"], start_time: "09:00", end_time: "17:00", utilization_pct: 70 }),
      row({ days: ["Tue", "Wed", "Thu"], start_time: "09:00", end_time: "17:00", utilization_pct: 70 }),
    ];
    const warnings = detectOverlaps(rows);
    // Shared days: Tue, Wed
    expect(warnings).toHaveLength(2);
    const days = warnings.map((w) => w.day);
    expect(days).toContain("Tue");
    expect(days).toContain("Wed");
  });

  it("handles adjacent (touching) time ranges without warning", () => {
    const rows = [
      row({ days: ["Mon"], start_time: "09:00", end_time: "12:00", utilization_pct: 100 }),
      row({ days: ["Mon"], start_time: "12:00", end_time: "17:00", utilization_pct: 100 }),
    ];
    // 12:00 == 12:00, so overlapStart >= overlapEnd → no overlap
    expect(detectOverlaps(rows)).toEqual([]);
  });

  it("handles three rows with pairwise overlaps", () => {
    const rows = [
      row({ days: ["Mon"], start_time: "09:00", end_time: "17:00", utilization_pct: 60 }),
      row({ days: ["Mon"], start_time: "10:00", end_time: "15:00", utilization_pct: 60 }),
      row({ days: ["Mon"], start_time: "14:00", end_time: "18:00", utilization_pct: 60 }),
    ];
    const warnings = detectOverlaps(rows);
    // Pairs: (0,1) overlap 10:00-15:00 = 120%, (0,2) overlap 14:00-17:00 = 120%, (1,2) overlap 14:00-15:00 = 120%
    expect(warnings).toHaveLength(3);
    const pairs = warnings.map((w) => w.rowIndices);
    expect(pairs).toContainEqual([0, 1]);
    expect(pairs).toContainEqual([0, 2]);
    expect(pairs).toContainEqual([1, 2]);
  });

  it("returns empty for 0% utilization rows", () => {
    const rows = [
      row({ days: ["Mon"], start_time: "09:00", end_time: "17:00", utilization_pct: 0 }),
      row({ days: ["Mon"], start_time: "09:00", end_time: "17:00", utilization_pct: 0 }),
    ];
    expect(detectOverlaps(rows)).toEqual([]);
  });

  it("detects overlap at exactly 101% combined", () => {
    const rows = [
      row({ days: ["Fri"], start_time: "08:00", end_time: "12:00", utilization_pct: 51 }),
      row({ days: ["Fri"], start_time: "10:00", end_time: "14:00", utilization_pct: 51 }),
    ];
    const warnings = detectOverlaps(rows);
    expect(warnings).toHaveLength(1);
    expect(warnings[0].combinedUtilization).toBe(102);
  });
});
