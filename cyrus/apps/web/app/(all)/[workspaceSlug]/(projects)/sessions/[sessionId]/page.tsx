/**
 * Session Detail Page — /:workspaceSlug/sessions/:sessionId
 */

import type { Route } from "./+types/page";
import { SessionDetail } from "@/components/sessions";

export default function SessionDetailPage({ params }: Route.ComponentProps) {
  const { workspaceSlug, sessionId } = params;

  return <SessionDetail workspaceSlug={workspaceSlug} sessionId={sessionId} />;
}
