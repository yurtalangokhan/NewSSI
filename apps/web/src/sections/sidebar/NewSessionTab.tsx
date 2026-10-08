"use client";

import { useTranslation } from "react-i18next";

import { SvgEditBig } from "@opal/icons";
import { useAppMode } from "@/providers/AppModeProvider";
import SidebarTab from "@/refresh-components/buttons/SidebarTab";

interface NewSessionTabProps {
  href: string;
  folded: boolean;
  /** Whether the current page already is a new session. */
  isNewSession: boolean;
}

/**
 * The sidebar's "New Session" entry. Clicking it on the new session page
 * starts over (fresh mode and search page); from any other session the
 * navigation to `href` does that on arrival.
 */
export default function NewSessionTab({
  href,
  folded,
  isNewSession,
}: NewSessionTabProps) {
  const { t } = useTranslation();
  const { startNewSession } = useAppMode();

  return (
    <div data-testid="AppSidebar/new-session">
      <SidebarTab
        leftIcon={SvgEditBig}
        folded={folded}
        href={href}
        transient={isNewSession}
        onClick={() => {
          if (isNewSession) startNewSession();
        }}
      >
        {t("sidebar.newSession")}
      </SidebarTab>
    </div>
  );
}
