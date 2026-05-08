import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function PATCH(request: NextRequest) {
  return proxyToBackend(request, "/api/auto-scroll", {
    method: "PATCH",
    withCredentials: true,
  });
}
