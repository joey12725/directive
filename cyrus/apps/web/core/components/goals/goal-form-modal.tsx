/**
 * Goal create/edit modal.
 */

import { useState, useEffect } from "react";
import { Dialog, EDialogWidth } from "@plane/propel/dialog";
import { Button } from "@plane/propel/button";

interface GoalFormData {
  name: string;
  description: string;
  status: string;
  deadline: string;
}

interface GoalFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: Record<string, unknown>) => Promise<void>;
  initialData?: Partial<GoalFormData>;
  mode: "create" | "edit";
}

const EMPTY: GoalFormData = { name: "", description: "", status: "active", deadline: "" };

export function GoalFormModal({ isOpen, onClose, onSubmit, initialData, mode }: GoalFormModalProps) {
  const [form, setForm] = useState<GoalFormData>(EMPTY);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setForm({
        name: initialData?.name ?? "",
        description: initialData?.description ?? "",
        status: initialData?.status ?? "active",
        deadline: initialData?.deadline ? initialData.deadline.slice(0, 10) : "",
      });
    }
  }, [isOpen, initialData]);

  const handleSubmit = async () => {
    if (!form.name.trim()) return;
    setLoading(true);
    try {
      await onSubmit({
        ...form,
        deadline: form.deadline || null as unknown as string,
      });
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Panel width={EDialogWidth.MD}>
        <Dialog.Title>{mode === "create" ? "Create Goal" : "Edit Goal"}</Dialog.Title>

        <div className="space-y-4 mt-4">
          <div>
            <label className="text-caption-sm-medium text-tertiary block mb-1">Name *</label>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Ship Dashboard v2"
              className="w-full rounded-md border border-subtle bg-surface-1 px-3 py-2 text-body-sm text-primary placeholder:text-tertiary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
              autoFocus
            />
          </div>

          <div>
            <label className="text-caption-sm-medium text-tertiary block mb-1">Description</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="What does this goal aim to achieve?"
              rows={3}
              className="w-full rounded-md border border-subtle bg-surface-1 px-3 py-2 text-body-sm text-primary placeholder:text-tertiary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary resize-none"
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <label className="text-caption-sm-medium text-tertiary block mb-1">Status</label>
              <select
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
                className="w-full rounded-md border border-subtle bg-surface-1 px-3 py-2 text-body-sm text-primary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
              >
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="archived">Archived</option>
              </select>
            </div>

            <div className="flex-1">
              <label className="text-caption-sm-medium text-tertiary block mb-1">Deadline</label>
              <input
                type="date"
                value={form.deadline}
                onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                className="w-full rounded-md border border-subtle bg-surface-1 px-3 py-2 text-body-sm text-primary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading} disabled={!form.name.trim()}>
            {mode === "create" ? "Create Goal" : "Save Changes"}
          </Button>
        </div>
      </Dialog.Panel>
    </Dialog>
  );
}
