/**
 * Cyrus settings sidebar navigation.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useParams } from "react-router";
import {
  Settings,
  Users,
  Bot,
  Server,
  Calendar,
  Radio,
  Bell,
  ShieldCheck,
  Cpu,
  Layers,
  Plug,
  Cog,
} from "lucide-react";
import { cn } from "@plane/utils";
import type { LucideIcon } from "lucide-react";

interface NavItem {
  key: string;
  label: string;
  icon: LucideIcon;
  href: string;
}

interface NavCategory {
  title: string;
  items: NavItem[];
}

const NAV_CATEGORIES: NavCategory[] = [
  {
    title: "General",
    items: [
      { key: "general", label: "General", icon: Settings, href: "/settings/cyrus" },
      { key: "members", label: "Members", icon: Users, href: "/settings/cyrus/members" },
    ],
  },
  {
    title: "Agents & Compute",
    items: [
      { key: "agents", label: "Agents", icon: Bot, href: "/settings/cyrus/agents" },
      { key: "pools", label: "Compute Pools", icon: Server, href: "/settings/cyrus/pools" },
      { key: "schedules", label: "Schedules", icon: Calendar, href: "/settings/cyrus/schedules" },
      { key: "relays", label: "Relays", icon: Radio, href: "/settings/cyrus/relays" },
      { key: "model-tiers", label: "Model Tiers", icon: Layers, href: "/settings/cyrus/model-tiers" },
    ],
  },
  {
    title: "Orchestration",
    items: [
      { key: "orchestrator", label: "Orchestrator Config", icon: Cpu, href: "/settings/cyrus/orchestrator" },
      { key: "approvals", label: "Approvals", icon: ShieldCheck, href: "/settings/cyrus/approvals" },
      { key: "notifications", label: "Notifications", icon: Bell, href: "/settings/cyrus/notifications" },
    ],
  },
  {
    title: "Integrations",
    items: [
      { key: "openclaw", label: "OpenClaw Connection", icon: Cog, href: "/settings/cyrus/openclaw" },
      { key: "external-api", label: "External API", icon: Plug, href: "/settings/cyrus/external-api" },
    ],
  },
];

function SidebarItem({ item, isActive, workspaceSlug }: { item: NavItem; isActive: boolean; workspaceSlug: string }) {
  return (
    <Link
      href={`/${workspaceSlug}${item.href}`}
      className={cn(
        "flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-body-sm-medium text-secondary transition-colors",
        {
          "bg-layer-transparent-selected text-primary": isActive,
          "hover:bg-layer-transparent-hover": !isActive,
        }
      )}
    >
      <span className="grid size-4 shrink-0 place-items-center">
        <item.icon className="size-3.5" />
      </span>
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

export function CyrusSettingsSidebar() {
  const { workspaceSlug } = useParams<{ workspaceSlug: string }>();
  const pathname = usePathname();

  return (
    <div className="h-full w-[250px] shrink-0 overflow-y-auto border-r border-r-subtle bg-surface-1">
      {/* Header */}
      <div className="px-5 pt-5 pb-2">
        <h2 className="text-body-md-medium text-primary">Cyrus Settings</h2>
        <p className="text-caption-sm text-tertiary mt-0.5">Agent orchestration configuration</p>
      </div>

      {/* Navigation */}
      <div className="mt-3 flex flex-col divide-y divide-subtle px-3">
        {NAV_CATEGORIES.map((category) => (
          <div key={category.title} className="shrink-0 py-3 first:pt-0 last:pb-0">
            <div className="p-2 text-caption-md-medium text-tertiary">{category.title}</div>
            <div className="flex flex-col">
              {category.items.map((item) => {
                const fullPath = `/${workspaceSlug}${item.href}`;
                const isActive = item.href === "/settings/cyrus"
                  ? pathname === fullPath || pathname === `${fullPath}/`
                  : pathname?.startsWith(fullPath) ?? false;

                return (
                  <SidebarItem
                    key={item.key}
                    item={item}
                    isActive={isActive}
                    workspaceSlug={workspaceSlug ?? ""}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
