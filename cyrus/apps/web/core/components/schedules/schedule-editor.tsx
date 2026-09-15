/**
 * ScheduleEditor — visual editor for a schedule's time blocks.
 *
 * Renders a dynamic list of ScheduleRow entries with time pickers,
 * weekday toggles, utilization sliders, and overlap validation.
 *
 * Props:
 *   - rows: initial row data (from API or empty)
 *   - onChange: called on every mutation with the full rows array
 */

import { useMemo, useCallback } from "react";
import { Plus, AlertTriangle, Clock } from "lucide-react";
import { Button } from "@plane/propel/button";
import { Card } from "@plane/propel/card";
import { ScheduleRowEditor } from "./schedule-row-editor";
import { detectOverlaps } from "./overlap-validation";
import { createDefaultRow } from "./types";
import type { ScheduleRowData, OverlapWarning } from "./types";

interface ScheduleEditorProps {
  rows: ScheduleRowData[];
  onChange: (rows: ScheduleRowData[]) => void;
}

export function ScheduleEditor({ rows, onChange }: ScheduleEditorProps) {
  // Detect overlaps whenever rows change
  const warnings = useMemo(() => detectOverlaps(rows), [rows]);

  // Build a set of row indices that have warnings
  const warningIndices = useMemo(() => {
    const set = new Set<number>();
    for (const w of warnings) {
      set.add(w.rowIndices[0]);
      set.add(w.rowIndices[1]);
    }
    return set;
  }, [warnings]);

  // Deduplicate warnings by row-pair for display
  const uniqueWarnings = useMemo(() => {
    const seen = new Set<string>();
    const result: OverlapWarning[] = [];
    for (const w of warnings) {
      const key = `${w.rowIndices[0]}-${w.rowIndices[1]}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(w);
      }
    }
    return result;
  }, [warnings]);

  const handleRowChange = useCallback(
    (index: number, updated: ScheduleRowData) => {
      const next = [...rows];
      next[index] = updated;
      onChange(next);
    },
    [rows, onChange]
  );

  const handleRowRemove = useCallback(
    (index: number) => {
      onChange(rows.filter((_, i) => i !== index));
    },
    [rows, onChange]
  );

  const handleAddRow = useCallback(() => {
    onChange([...rows, createDefaultRow()]);
  }, [rows, onChange]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock className="size-5 text-tertiary" />
          <h2 className="text-body-lg-medium text-primary">Schedule Time Blocks</h2>
        </div>
        <Button variant="secondary" size="base" prependIcon={<Plus />} onClick={handleAddRow}>
          Add Time Block
        </Button>
      </div>

      {/* Overlap warnings */}
      {uniqueWarnings.length > 0 && (
        <Card className="!border-warning-primary !bg-warning-subtle/30">
          <div className="flex gap-3">
            <AlertTriangle className="size-5 text-warning-primary flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="text-body-sm-medium text-warning-primary">Utilization exceeds 100%</p>
              {uniqueWarnings.map((w, i) => (
                <p key={i} className="text-caption-md text-warning-primary/80">
                  Blocks {w.rowIndices[0] + 1} &amp; {w.rowIndices[1] + 1} overlap on {w.day} ({w.overlapStart}–
                  {w.overlapEnd}) with {w.combinedUtilization}% combined utilization.
                </p>
              ))}
            </div>
          </div>
        </Card>
      )}

      {/* Row list */}
      {rows.length === 0 ? (
        <Card className="!py-12">
          <div className="flex flex-col items-center justify-center text-center">
            <Clock className="size-8 text-tertiary mb-3" />
            <p className="text-body-sm text-tertiary mb-4">
              No time blocks defined. Add one to start scheduling compute time.
            </p>
            <Button variant="primary" size="lg" prependIcon={<Plus />} onClick={handleAddRow}>
              Add Time Block
            </Button>
          </div>
        </Card>
      ) : (
        <div className="space-y-3">
          {rows.map((row, i) => (
            <ScheduleRowEditor
              key={row._key}
              row={row}
              index={i}
              onChange={handleRowChange}
              onRemove={handleRowRemove}
              hasWarning={warningIndices.has(i)}
            />
          ))}
        </div>
      )}

      {/* Summary footer */}
      {rows.length > 0 && (
        <div className="flex items-center justify-between pt-2 border-t border-subtle">
          <p className="text-caption-sm text-tertiary">
            {rows.length} time block{rows.length !== 1 ? "s" : ""} configured
          </p>
          <Button variant="secondary" size="base" prependIcon={<Plus />} onClick={handleAddRow}>
            Add Time Block
          </Button>
        </div>
      )}
    </div>
  );
}
