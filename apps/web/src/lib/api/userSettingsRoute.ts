import { proxyToBackend } from "@/lib/api/proxy";
import type { NextRequest } from "next/server";
import type { BackendTarget } from "@/lib/api/http/types";

/**
 * Creates a PATCH handler that proxies user-settings updates to the
 * domain-owned settings target without defining an upstream address.
 *
 * Used by auto-scroll, chat-background, default-app-mode, default-model,
 * and theme-preference routes — all of which are byte-identical PATCH
 * proxies.
 */
export function createSettingsPatchRoute(endpoint: {
  method: "PATCH";
  backend: BackendTarget;
}) {
  return function PATCH(request: NextRequest) {
    return proxyToBackend(request, endpoint.backend, {
      method: endpoint.method,
      withCredentials: true,
    });
  };
}
