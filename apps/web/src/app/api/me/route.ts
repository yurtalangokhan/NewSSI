import { proxyToBackend } from "@/lib/api/proxy";
import { USER_SERVICE_URL } from "@/lib/constants";
import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, "/api/auth/me", {
    backendUrl: USER_SERVICE_URL,
    method: "GET",
    withCredentials: true,
  });
}
