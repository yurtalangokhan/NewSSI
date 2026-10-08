"use client";

import { useTranslation } from "react-i18next";
import * as InputLayouts from "@/layouts/input-layouts";
import Switch from "@/refresh-components/inputs/Switch";
import useSidebarBackgroundTheme from "@/hooks/useSidebarBackgroundTheme";

/** Settings row that turns the TÜRKSAT sidebar theme on or off for this
 * device while an animated chat background is showing. */
export function SidebarBackgroundThemeToggle() {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useSidebarBackgroundTheme();

  return (
    <InputLayouts.Horizontal
      title={t("settings.general.sidebarThemeLabel")}
      description={t("settings.general.sidebarThemeDescription")}
    >
      <Switch checked={enabled} onCheckedChange={setEnabled} />
    </InputLayouts.Horizontal>
  );
}
