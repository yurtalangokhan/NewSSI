import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function PATCH(request: NextRequest) {
  return proxyToBackend(request, "/api/user/theme-preference", {
    method: "PATCH",
    withCredentials: true,
  });
}
