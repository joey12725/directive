/**
 * Individual event renderers for the session replay timeline.
 * Each component handles one event type from the NDJSON event_log.
 */

import { useState } from "react";
import {
  MessageSquareText,
  Wrench,
  Brain,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import type { SessionEvent } from "./types";

// ---------------------------------------------------------------------------
// Text Event
// ---------------------------------------------------------------------------
export function TextEvent({ event }: { event: SessionEvent }) {
  const content = event.text || event.content || "";
  if (!content) return null;

  return (
    <div className="flex gap-3 py-3">
      <div className="mt-0.5 flex-shrink-0">
        <MessageSquareText className="size-4 text-blue-500" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-body-sm text-primary whitespace-pre-wrap break-words">{content}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tool Call Event
// ---------------------------------------------------------------------------
export function ToolCallEvent({ event }: { event: SessionEvent }) {
  const [isOpen, setIsOpen] = useState(false);
  const toolName = event.tool_name || "unknown_tool";
  const isError = event.tool_status === "error";

  return (
    <div className="rounded-lg border border-subtle bg-surface-1 overflow-hidden">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-layer-2 transition-colors"
      >
        <Wrench className="size-4 flex-shrink-0 text-amber-500" />
        <span className="text-body-sm-medium text-primary flex-1 font-mono">{toolName}</span>
        {isError ? (
          <XCircle className="size-4 flex-shrink-0 text-red-500" />
        ) : (
          <CheckCircle2 className="size-4 flex-shrink-0 text-green-500" />
        )}
        {isOpen ? (
          <ChevronDown className="size-4 flex-shrink-0 text-tertiary" />
        ) : (
          <ChevronRight className="size-4 flex-shrink-0 text-tertiary" />
        )}
      </button>

      {isOpen && (
        <div className="border-t border-subtle px-4 py-3 space-y-3">
          {event.tool_args && Object.keys(event.tool_args).length > 0 && (
            <div>
              <p className="text-caption-sm-medium text-tertiary mb-1">Arguments</p>
              <pre className="text-caption-sm text-secondary bg-layer-3 rounded-md p-3 overflow-x-auto font-mono">
                {JSON.stringify(event.tool_args, null, 2)}
              </pre>
            </div>
          )}
          {event.tool_output && (
            <div>
              <p className="text-caption-sm-medium text-tertiary mb-1">Output</p>
              <pre
                className={`text-caption-sm rounded-md p-3 overflow-x-auto font-mono ${
                  isError ? "bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300" : "bg-layer-3 text-secondary"
                }`}
              >
                {event.tool_output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Thinking Event
// ---------------------------------------------------------------------------
export function ThinkingEvent({ event }: { event: SessionEvent }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const content = event.content || event.text || "";
  if (!content) return null;

  const isLong = content.length > 200;
  const displayContent = isLong && !isExpanded ? content.slice(0, 200) + "…" : content;

  return (
    <div className="flex gap-3 py-3">
      <div className="mt-0.5 flex-shrink-0">
        <Brain className="size-4 text-purple-400" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="rounded-lg bg-purple-50/50 dark:bg-purple-950/20 border border-purple-200/40 dark:border-purple-800/30 px-4 py-3">
          <p className="text-caption-md text-purple-700 dark:text-purple-300 italic whitespace-pre-wrap break-words">
            {displayContent}
          </p>
          {isLong && (
            <button
              type="button"
              onClick={() => setIsExpanded(!isExpanded)}
              className="mt-2 text-caption-sm-medium text-purple-500 hover:text-purple-700 dark:hover:text-purple-300"
            >
              {isExpanded ? "Show less" : "Show more"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error Event
// ---------------------------------------------------------------------------
export function ErrorEvent({ event }: { event: SessionEvent }) {
  const message = event.error || event.text || event.content || "Unknown error";
  return (
    <div className="flex gap-3 py-3">
      <div className="mt-0.5 flex-shrink-0">
        <AlertTriangle className="size-4 text-red-500" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="rounded-lg border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/30 px-4 py-3">
          <p className="text-body-sm-medium text-red-700 dark:text-red-300">{message}</p>
          {event.error_code && (
            <p className="mt-1 text-caption-sm text-red-500 font-mono">Code: {event.error_code}</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Unknown / Fallback Event
// ---------------------------------------------------------------------------
export function UnknownEvent({ event }: { event: SessionEvent }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="flex gap-3 py-2">
      <div className="mt-0.5 flex-shrink-0">
        <MessageSquareText className="size-4 text-tertiary" />
      </div>
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="text-caption-sm text-tertiary hover:text-secondary"
        >
          <span className="font-mono">{event.type || "unknown"}</span> event
          {isOpen ? " ▾" : " ▸"}
        </button>
        {isOpen && (
          <pre className="mt-2 text-caption-sm text-tertiary bg-layer-3 rounded-md p-3 overflow-x-auto font-mono">
            {JSON.stringify(event, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
