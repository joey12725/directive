/**
 * Cyrus settings layout — wraps all /settings/cyrus/* pages with sidebar.
 */

import { Outlet } from "react-router";
import { CyrusSettingsSidebar } from "@/components/cyrus-settings";

export default function CyrusSettingsLayout() {
  return (
    <div className="inset-y-0 flex h-full w-full flex-row">
      <div className="relative flex size-full">
        <div className="hidden h-full md:block">
          <CyrusSettingsSidebar />
        </div>
        <Outlet />
      </div>
    </div>
  );
}
