/**
 * Session event timeline — main feed that maps event_log entries
 * to their corresponding renderer components.
 */

import type { SessionEvent } from "./types";
import { TextEvent, ToolCallEvent, ThinkingEvent, ErrorEvent, UnknownEvent } from "./event-renderers";

function renderEvent(event: SessionEvent, index: number) {
  // Guard against malformed entries
  if (!event || typeof event !== "object") return null;

  const key = `event-${index}-${event.type || "unknown"}`;

  switch (event.type) {
    case "text":
    case "agent_message":
    case "agent_message_chunk":
      return <TextEvent key={key} event={event} />;

    case "tool_call":
    case "tool_use":
      return <ToolCallEvent key={key} event={event} />;

    case "thinking":
    case "reasoning":
      return <ThinkingEvent key={key} event={event} />;

    case "error":
      return <ErrorEvent key={key} event={event} />;

    // System events that are useful to show but not primary
    case "session_started":
    case "thread.started":
      return (
        <div key={key} className="flex items-center gap-2 py-2 text-caption-sm text-tertiary">
          <div className="size-1.5 rounded-full bg-green-500" />
          Session started
          {event.session_id && <span className="font-mono">({event.session_id})</span>}
          {event.model && <span className="font-mono">· {event.model}</span>}
        </div>
      );

    case "done":
    case "relay_exit":
      return (
        <div key={key} className="flex items-center gap-2 py-2 text-caption-sm text-tertiary">
          <div className="size-1.5 rounded-full bg-gray-400" />
          {event.type === "done" ? "Session completed" : "Relay exited"}
          {event.usage && (
            <span className="font-mono">
              · {event.usage.total_tokens ?? (event.usage.input_tokens ?? 0) + (event.usage.output_tokens ?? 0)} tokens
            </span>
          )}
        </div>
      );

    case "item.completed":
      return (
        <TextEvent
          key={key}
          event={{ ...event, text: (event.item as Record<string, string> | undefined)?.text || event.text || "", type: "text" } as SessionEvent}
        />
      );

    default:
      return <UnknownEvent key={key} event={event} />;
  }
}

interface EventTimelineProps {
  events: SessionEvent[];
}

export function EventTimeline({ events }: EventTimelineProps) {
  if (!events || events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-body-sm text-tertiary">No events recorded for this session.</p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-subtle">
      {events.map((event, i) => renderEvent(event, i))}
    </div>
  );
}
