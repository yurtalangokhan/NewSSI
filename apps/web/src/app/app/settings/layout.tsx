"use client";

import { usePathname } from "next/navigation";
import * as AppLayouts from "@/layouts/app-layouts";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import SidebarTab from "@/refresh-components/buttons/SidebarTab";
import { SvgSliders } from "@opal/icons";
import { useTranslation } from "react-i18next";

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const pathname = usePathname();
  const { t } = useTranslation();

  return (
    <AppLayouts.Root>
      <SettingsLayouts.Root width="lg">
        <SettingsLayouts.Header icon={SvgSliders} title={t("settingsLayout.title")} separator />

        <SettingsLayouts.Body>
          <div className="grid grid-cols-[auto_1fr]">
            {/* Left: Tab Navigation */}
            <div className="flex flex-col px-2 w-[12.5rem]">
              <SidebarTab
                href="/app/settings/general"
                transient={pathname === "/app/settings/general"}
              >
                {t("settingsLayout.generalTab")}
              </SidebarTab>
              <SidebarTab
                href="/app/settings/chat-preferences"
                transient={pathname === "/app/settings/chat-preferences"}
              >
                {t("settingsLayout.chatPreferencesTab")}
              </SidebarTab>
            </div>

            {/* Right: Tab Content */}
            <div className="px-4">{children}</div>
          </div>
        </SettingsLayouts.Body>
      </SettingsLayouts.Root>
    </AppLayouts.Root>
  );
}
