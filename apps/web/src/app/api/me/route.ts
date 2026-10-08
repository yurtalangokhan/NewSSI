import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";

import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";
import { appSettings } from "@/lib/settings";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, sessionEndpoints.getCurrentUser.backend, {
    method: "GET",
    withCredentials: true,
  });
}
