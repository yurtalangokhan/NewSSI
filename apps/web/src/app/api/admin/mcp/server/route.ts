import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function POST(request: NextRequest) {
  return proxyToBackend(request, "/api/admin/mcp/server", { method: "POST" });
}
