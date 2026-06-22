import { proxyToBackend } from "@/lib/api/proxy";
import { USER_SERVICE_URL } from "@/lib/constants";
import { NextRequest } from "next/server";

export async function PATCH(request: NextRequest) {
  return proxyToBackend(request, "/api/users/me/settings/", {
    backendUrl: USER_SERVICE_URL,
    method: "PATCH",
    withCredentials: true,
  });
}
