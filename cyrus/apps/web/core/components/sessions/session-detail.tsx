/**
 * SessionDetail — the main Session Replay Viewer component.
 *
 * Layout: responsive grid with main event feed + metadata sidebar.
 * Fetches session data via SWR and renders the event timeline.
 */

import { ArrowLeft } from "lucide-react";
import useSWR from "swr";
import { Button } from "@plane/propel/button";
import { Skeleton } from "@plane/propel/skeleton";
import { sessionService } from "@/services/session.service";
import { EventTimeline } from "./event-timeline";
import { SessionMetadata } from "./session-metadata";
import { MOCK_SESSION } from "./mock-session";
import type { Session } from "./types";

// Set to true to render with mock data (no backend needed)
const USE_MOCK = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("mock") === "1";

interface SessionDetailProps {
  workspaceSlug: string;
  sessionId: string;
}

function SessionDetailSkeleton() {
  return (
    <div className="flex flex-col lg:flex-row gap-6 p-6">
      <div className="flex-1 min-w-0">
        <Skeleton>
          <Skeleton.Item height="32px" width="60%" />
          <Skeleton.Item height="16px" width="40%" className="mt-3" />
          <Skeleton.Item height="80px" width="100%" className="mt-6" />
          <Skeleton.Item height="60px" width="100%" className="mt-4" />
          <Skeleton.Item height="100px" width="100%" className="mt-4" />
          <Skeleton.Item height="60px" width="100%" className="mt-4" />
        </Skeleton>
      </div>
      <div className="w-full lg:w-80 flex-shrink-0">
        <Skeleton>
          <Skeleton.Item height="400px" width="100%" />
        </Skeleton>
      </div>
    </div>
  );
}

function SessionDetailError({ error }: { error: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 px-6 text-center">
      <div className="rounded-full bg-red-100 dark:bg-red-950/30 p-4 mb-4">
        <span className="text-2xl">⚠</span>
      </div>
      <h2 className="text-body-lg-medium text-primary mb-2">Failed to load session</h2>
      <p className="text-body-sm text-tertiary max-w-md">{error}</p>
    </div>
  );
}

export function SessionDetail({ workspaceSlug, sessionId }: SessionDetailProps) {
  const {
    data: session,
    error,
    isLoading,
  } = useSWR<Session>(
    USE_MOCK ? null : `SESSION_${workspaceSlug}_${sessionId}`,
    () => sessionService.getSession(workspaceSlug, sessionId)
  );

  const displaySession = USE_MOCK ? MOCK_SESSION : session;

  if (isLoading && !USE_MOCK) return <SessionDetailSkeleton />;
  if (error && !USE_MOCK) return <SessionDetailError error={error?.data?.detail || "Could not fetch session data."} />;
  if (!displaySession) return <SessionDetailError error="Session not found." />;

  const eventCount = displaySession.event_log?.length ?? 0;

  return (
    <div className="h-full overflow-y-auto">
      {/* Top bar */}
      <div className="sticky top-0 z-10 bg-surface-0 border-b border-subtle px-6 py-3 flex items-center gap-3">
        <Button
          variant="ghost"
          size="sm"
          prependIcon={<ArrowLeft />}
          onClick={() => window.history.back()}
        >
          Back
        </Button>
        <div className="h-4 w-px bg-subtle" />
        <h1 className="text-body-md-medium text-primary truncate">
          Session Replay
        </h1>
        <span className="text-caption-sm text-tertiary font-mono hidden sm:inline">
          {displaySession.acpx_session_id || displaySession.id.slice(0, 8)}
        </span>
        <span className="text-caption-sm text-tertiary ml-auto">
          {eventCount} event{eventCount !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Main content: feed + sidebar */}
      <div className="flex flex-col lg:flex-row gap-6 p-6">
        {/* Event Feed */}
        <div className="flex-1 min-w-0">
          <EventTimeline events={displaySession.event_log || []} />
        </div>

        {/* Metadata Sidebar */}
        <div className="w-full lg:w-80 flex-shrink-0 order-first lg:order-last">
          <SessionMetadata session={displaySession} workspaceSlug={workspaceSlug} />
        </div>
      </div>
    </div>
  );
}
