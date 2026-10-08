"use client";

import { useTranslation } from "react-i18next";
import * as InputLayouts from "@/layouts/input-layouts";
import Switch from "@/refresh-components/inputs/Switch";
import useBackgroundAnimation from "@/hooks/useBackgroundAnimation";

/** Settings row that turns the animated (canvas) chat backgrounds on or off
 * for this device; off paints the scene once as a still frame. */
export function BackgroundAnimationToggle() {
  const { t } = useTranslation();
  const [animate, setAnimate] = useBackgroundAnimation();

  return (
    <InputLayouts.Horizontal
      title={t("settings.general.animateBackgroundLabel")}
      description={t("settings.general.animateBackgroundDescription")}
    >
      <Switch checked={animate} onCheckedChange={setAnimate} />
    </InputLayouts.Horizontal>
  );
}
