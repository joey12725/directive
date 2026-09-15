/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import {
  AnalyticsIcon,
  ArchiveIcon,
  CycleIcon,
  DashboardIcon,
  DraftIcon,
  HomeIcon,
  InboxIcon,
  MultipleStickyIcon,
  ProjectIcon,
  ViewsIcon,
  YourWorkIcon,
} from "@plane/propel/icons";
import { Bot, Target, Server, Play, Settings } from "lucide-react";
import { cn } from "@plane/utils";

export const getSidebarNavigationItemIcon = (key: string, className: string = "") => {
  const cls = cn("size-4 flex-shrink-0", className);
  switch (key) {
    case "home":
      return <DashboardIcon className={cls} />;
    case "inbox":
      return <InboxIcon className={cls} />;
    case "projects":
      return <ProjectIcon className={cls} />;
    case "views":
      return <ViewsIcon className={cls} />;
    case "active_cycles":
      return <CycleIcon className={cls} />;
    case "analytics":
      return <AnalyticsIcon className={cls} />;
    case "your_work":
      return <YourWorkIcon className={cls} />;
    case "drafts":
      return <DraftIcon className={cls} />;
    case "archives":
      return <ArchiveIcon className={cls} />;
    case "stickies":
      return <MultipleStickyIcon className={cls} />;
    // Cyrus navigation items
    case "goals":
      return <Target className={cls} />;
    case "agents":
      return <Bot className={cls} />;
    case "pools":
      return <Server className={cls} />;
    case "sessions":
      return <Play className={cls} />;
    case "cyrus_settings":
      return <Settings className={cls} />;
  }
};
