import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/api/proxy";
import { USER_SERVICE_URL } from "@/lib/constants";
import { getDomain } from "@/lib/redirectSS";

export async function POST(request: NextRequest) {
  const callbackBase = getDomain(request).replace(/\/$/, "");
  return proxyToBackend(request, "/api/auth/external/login", {
    method: "POST",
    backendUrl: USER_SERVICE_URL,
    queryParams: {
      redirect_uri: `${callbackBase}/auth/oidc/callback`,
    },
  });
}
