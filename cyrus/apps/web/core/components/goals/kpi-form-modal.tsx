/**
 * KPI create/edit modal.
 */

import { useState, useEffect } from "react";
import { Dialog, EDialogWidth } from "@plane/propel/dialog";
import { Button } from "@plane/propel/button";

interface KPIFormData {
  name: string;
  unit: string;
  current_value: string;
}

interface KPIFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: Record<string, unknown>) => Promise<void>;
  initialData?: Partial<KPIFormData>;
  mode: "create" | "edit";
}

export function KPIFormModal({ isOpen, onClose, onSubmit, initialData, mode }: KPIFormModalProps) {
  const [form, setForm] = useState<KPIFormData>({ name: "", unit: "", current_value: "" });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setForm({
        name: initialData?.name ?? "",
        unit: initialData?.unit ?? "",
        current_value: initialData?.current_value ?? "",
      });
    }
  }, [isOpen, initialData]);

  const handleSubmit = async () => {
    if (!form.name.trim()) return;
    setLoading(true);
    try {
      await onSubmit({
        name: form.name,
        unit: form.unit,
        current_value: form.current_value ? parseFloat(form.current_value) : null,
      });
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Panel width={EDialogWidth.SM}>
        <Dialog.Title>{mode === "create" ? "Add KPI" : "Edit KPI"}</Dialog.Title>

        <div className="space-y-4 mt-4">
          <div>
            <label className="text-caption-sm-medium text-tertiary block mb-1">KPI Name *</label>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. API Latency p99"
              className="w-full rounded-md border border-subtle bg-surface-1 px-3 py-2 text-body-sm text-primary placeholder:text-tertiary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
              autoFocus
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <label className="text-caption-sm-medium text-tertiary block mb-1">Unit</label>
              <input
                value={form.unit}
                onChange={(e) => setForm({ ...form, unit: e.target.value })}
                placeholder="e.g. ms, %, count"
                className="w-full rounded-md border border-subtle bg-surface-1 px-3 py-2 text-body-sm text-primary placeholder:text-tertiary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
              />
            </div>

            <div className="flex-1">
              <label className="text-caption-sm-medium text-tertiary block mb-1">Current Value</label>
              <input
                type="number"
                step="any"
                value={form.current_value}
                onChange={(e) => setForm({ ...form, current_value: e.target.value })}
                placeholder="0"
                className="w-full rounded-md border border-subtle bg-surface-1 px-3 py-2 text-body-sm text-primary placeholder:text-tertiary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading} disabled={!form.name.trim()}>
            {mode === "create" ? "Add KPI" : "Save"}
          </Button>
        </div>
      </Dialog.Panel>
    </Dialog>
  );
}
