import { NextRequest } from "next/server";
import { proxyToBackend } from "@/lib/api/proxy";
import { USER_SERVICE_URL } from "@/lib/constants";

export async function POST(request: NextRequest) {
  return proxyToBackend(request, "/api/auth/register", {
    method: "POST",
    backendUrl: USER_SERVICE_URL,
  });
}
