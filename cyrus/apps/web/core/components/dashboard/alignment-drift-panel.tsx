/**
 * AlignmentDriftPanel — shows agents with degraded/errored status.
 * Each row has a "Confirm Alignment" button and feedback text input.
 */

import { useState } from "react";
import { Compass, CheckCircle2, Send } from "lucide-react";
import { Card } from "@plane/propel/card";
import { Badge } from "@plane/propel/badge";
import { Button } from "@plane/propel/button";
import type { AgentHealthRow } from "./types";

interface AlignmentDriftPanelProps {
  agents: AgentHealthRow[];
  onConfirmAlignment?: (agentId: string, feedback: string) => void;
}

function DriftRow({
  agent,
  onConfirm,
}: {
  agent: AgentHealthRow;
  onConfirm?: (agentId: string, feedback: string) => void;
}) {
  const [feedback, setFeedback] = useState("");
  const [confirmed, setConfirmed] = useState(false);

  const handleConfirm = () => {
    onConfirm?.(agent.id, feedback);
    setConfirmed(true);
  };

  if (confirmed) {
    return (
      <div className="flex items-center gap-2 py-3">
        <CheckCircle2 className="size-4 text-success-primary" />
        <span className="text-body-sm text-success-primary">Alignment confirmed for {agent.name}</span>
      </div>
    );
  }

  return (
    <div className="py-3 space-y-2">
      <div className="flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-body-sm-medium text-primary truncate">{agent.name}</span>
            <Badge
              variant={agent.status === "errored" ? "danger" : "warning"}
              size="sm"
            >
              {agent.status}
            </Badge>
          </div>
          <p className="text-caption-sm text-tertiary mt-0.5">
            {agent.agent_type} · {agent.failed_7d} failures this week · {agent.success_rate_7d_pct}% success rate
          </p>
        </div>
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="Corrective feedback (optional)..."
          className="flex-1 rounded-md border border-subtle bg-surface-1 px-3 py-1.5 text-body-sm text-primary placeholder:text-tertiary focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
        />
        <Button
          variant="primary"
          size="base"
          prependIcon={<Send />}
          onClick={handleConfirm}
        >
          Confirm
        </Button>
      </div>
    </div>
  );
}

export function AlignmentDriftPanel({ agents, onConfirmAlignment }: AlignmentDriftPanelProps) {
  const driftAgents = agents.filter((a) => a.status === "degraded" || a.status === "errored");

  return (
    <Card>
      <div className="flex items-center gap-2 mb-3">
        <Compass className="size-4 text-tertiary" />
        <h3 className="text-body-sm-medium text-primary">Alignment Drift</h3>
        {driftAgents.length > 0 && <Badge variant="warning" size="sm">{driftAgents.length}</Badge>}
      </div>

      {driftAgents.length === 0 ? (
        <div className="flex items-center gap-2 py-4 justify-center">
          <CheckCircle2 className="size-4 text-success-primary" />
          <p className="text-body-sm text-tertiary">All agents aligned. No drift detected.</p>
        </div>
      ) : (
        <div className="divide-y divide-subtle">
          {driftAgents.map((agent) => (
            <DriftRow key={agent.id} agent={agent} onConfirm={onConfirmAlignment} />
          ))}
        </div>
      )}
    </Card>
  );
}
