import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";
import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/api/proxy";
import { getDomain } from "@/lib/navigation/redirect.server";

export async function POST(request: NextRequest) {
  const callbackBase = getDomain(request).replace(/\/$/, "");
  return proxyToBackend(request, sessionEndpoints.externalLogin.backend, {
    method: "POST",
    queryParams: {
      redirect_uri: `${callbackBase}/auth/oidc/callback`,
    },
  });
}
