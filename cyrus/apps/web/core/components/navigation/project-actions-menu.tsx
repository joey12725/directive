/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState, useRef } from "react";
import { useNavigate } from "react-router";
import { LogOut, MoreHorizontal, Settings, ArchiveIcon } from "lucide-react";
// plane imports
import { MEMBER_TRACKER_ELEMENTS } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { LinkIcon } from "@plane/propel/icons";
import { CustomMenu } from "@plane/ui";

type Props = {
  workspaceSlug: string;
  project: {
    id: string;
  };
  isAuthorized: boolean;
  onCopyText: () => void;
  onLeaveProject: () => void;
};

export function ProjectActionsMenu({
  workspaceSlug,
  project,
  isAuthorized,
  onCopyText,
  onLeaveProject,
}: Props) {
  // states
  const [isMenuActive, setIsMenuActive] = useState(false);
  // translation
  const { t } = useTranslation();
  // refs
  const actionSectionRef = useRef<HTMLDivElement | null>(null);
  // router
  const navigate = useNavigate();

  return (
    <CustomMenu
      customButton={
        <span
          ref={actionSectionRef}
          className="grid place-items-center rounded-sm p-0.5 text-placeholder hover:bg-layer-1"
          onClick={() => setIsMenuActive(!isMenuActive)}
        >
          <MoreHorizontal className="size-4" />
        </span>
      }
      className="flex-shrink-0"
      customButtonClassName="grid place-items-center"
      placement="bottom-start"
      ariaLabel={t("aria_labels.projects_sidebar.toggle_quick_actions_menu")}
      useCaptureForOutsideClick
      closeOnSelect
      onMenuClose={() => setIsMenuActive(false)}
    >
      <CustomMenu.MenuItem onClick={onCopyText}>
        <span className="flex items-center justify-start gap-2">
          <LinkIcon className="h-3.5 w-3.5 stroke-[1.5]" />
          <span>{t("copy_link")}</span>
        </span>
      </CustomMenu.MenuItem>
      {isAuthorized && (
        <CustomMenu.MenuItem
          onClick={() => {
            navigate(`/${workspaceSlug}/projects/${project?.id}/archives/issues`);
          }}
        >
          <div className="flex cursor-pointer items-center justify-start gap-2">
            <ArchiveIcon className="h-3.5 w-3.5 stroke-[1.5]" />
            <span>{t("archives")}</span>
          </div>
        </CustomMenu.MenuItem>
      )}
      <CustomMenu.MenuItem
        onClick={() => {
          navigate(`/${workspaceSlug}/settings/projects/${project?.id}`);
        }}
      >
        <div className="flex cursor-pointer items-center justify-start gap-2">
          <Settings className="h-3.5 w-3.5 stroke-[1.5]" />
          <span>{t("settings")}</span>
        </div>
      </CustomMenu.MenuItem>
      {/* Leave project */}
      {!isAuthorized && (
        <CustomMenu.MenuItem
          onClick={onLeaveProject}
          data-ph-element={MEMBER_TRACKER_ELEMENTS.SIDEBAR_PROJECT_QUICK_ACTIONS}
        >
          <div className="flex items-center justify-start gap-2">
            <LogOut className="h-3.5 w-3.5 stroke-[1.5]" />
            <span>{t("leave_project")}</span>
          </div>
        </CustomMenu.MenuItem>
      )}
    </CustomMenu>
  );
}
