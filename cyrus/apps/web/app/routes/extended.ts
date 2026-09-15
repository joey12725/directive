/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { layout, route } from "@react-router/dev/routes";
import type { RouteConfigEntry } from "@react-router/dev/routes";

export const extendedRoutes: RouteConfigEntry[] = [
  layout("./(all)/layout.tsx", [
    layout("./(all)/[workspaceSlug]/layout.tsx", [
      // ==================================================================
      // PROJECTS-SCOPED ROUTES (list views + detail pages)
      // ==================================================================
      layout("./(all)/[workspaceSlug]/(projects)/layout.tsx", [
        // Dashboard
        route(":workspaceSlug/dashboard", "./(all)/[workspaceSlug]/(projects)/dashboard/page.tsx"),

        // List views
        route(":workspaceSlug/goals", "./(all)/[workspaceSlug]/(projects)/goals/page.tsx"),
        route(":workspaceSlug/goals/:goalId", "./(all)/[workspaceSlug]/(projects)/goals/[goalId]/page.tsx"),
        route(":workspaceSlug/agents", "./(all)/[workspaceSlug]/(projects)/agents/page.tsx"),
        route(":workspaceSlug/pools", "./(all)/[workspaceSlug]/(projects)/pools/page.tsx"),
        route(":workspaceSlug/sessions", "./(all)/[workspaceSlug]/(projects)/sessions-list/page.tsx"),

        // Session detail (replay viewer)
        route(":workspaceSlug/sessions/:sessionId", "./(all)/[workspaceSlug]/(projects)/sessions/[sessionId]/page.tsx"),
      ]),

      // ==================================================================
      // CYRUS SETTINGS — nested under (settings) layout directly,
      // bypassing the (workspace) layout's access check
      // ==================================================================
      layout("./(all)/[workspaceSlug]/(settings)/layout.tsx", [
        layout(
          "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/layout.tsx",
          [
            route(":workspaceSlug/settings/cyrus", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/page.tsx"),
            route(":workspaceSlug/settings/cyrus/members", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/members/page.tsx"),
            route(":workspaceSlug/settings/cyrus/agents", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/agents/page.tsx"),
            route(":workspaceSlug/settings/cyrus/pools", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/pools/page.tsx"),
            route(":workspaceSlug/settings/cyrus/schedules", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/schedules/page.tsx"),
            route(":workspaceSlug/settings/cyrus/relays", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/relays/page.tsx"),
            route(":workspaceSlug/settings/cyrus/notifications", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/notifications/page.tsx"),
            route(":workspaceSlug/settings/cyrus/approvals", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/approvals/page.tsx"),
            route(":workspaceSlug/settings/cyrus/orchestrator", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/orchestrator/page.tsx"),
            route(":workspaceSlug/settings/cyrus/model-tiers", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/model-tiers/page.tsx"),
            route(":workspaceSlug/settings/cyrus/openclaw", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/openclaw/page.tsx"),
            route(":workspaceSlug/settings/cyrus/external-api", "./(all)/[workspaceSlug]/(settings)/settings/(workspace)/cyrus/external-api/page.tsx"),
          ]
        ),
      ]),
    ]),
  ]),
];
