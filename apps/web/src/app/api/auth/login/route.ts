import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";
import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/api/proxy";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, sessionEndpoints.getLogin.backend, {
    method: "GET",
  });
}

export async function POST(request: NextRequest) {
  return proxyToBackend(request, sessionEndpoints.login.backend, {
    method: "POST",
  });
}
