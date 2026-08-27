import { proxyToBackend } from "@/lib/api/proxy";
import { USER_SERVICE_URL } from "@/lib/constants";
import type { NextRequest } from "next/server";

/**
 * Creates a PATCH handler that proxies user-settings updates to the
 * backend user-service `/api/users/me/settings/` endpoint.
 *
 * Used by auto-scroll, chat-background, default-app-mode, default-model,
 * and theme-preference routes — all of which are byte-identical PATCH
 * proxies.
 */
export function createSettingsPatchRoute() {
  return function PATCH(request: NextRequest) {
    return proxyToBackend(request, "/api/users/me/settings/", {
      backendUrl: USER_SERVICE_URL,
      method: "PATCH",
      withCredentials: true,
    });
  };
}
