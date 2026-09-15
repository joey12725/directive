/**
 * Executive Dashboard Page — /:workspaceSlug/dashboard
 */

import type { Route } from "./+types/page";
import { ExecutiveDashboard } from "@/components/dashboard";

export default function DashboardPage({ params }: Route.ComponentProps) {
  return <ExecutiveDashboard workspaceSlug={params.workspaceSlug} />;
}
