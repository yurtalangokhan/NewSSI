"use client";

import createDeviceFlagHook from "@/hooks/createDeviceFlagHook";

/**
 * Whether animated (canvas) chat backgrounds should move, and a setter.
 *
 * A device-level display preference — a low-power laptop or a tablet wants it
 * off even if the same account's desktop does not. Defaults to animating
 * (including on the server, where the value only affects an effect, never
 * markup).
 */
const useBackgroundAnimation = createDeviceFlagHook({
  storageKey: "agentic_background_animation",
  changeEvent: "agentic:background-animation-change",
});

export default useBackgroundAnimation;
