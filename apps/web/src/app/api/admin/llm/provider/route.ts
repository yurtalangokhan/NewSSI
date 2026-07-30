import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, "/admin/llm/provider");
}

export async function PUT(request: NextRequest) {
  return proxyToBackend(request, "/api/admin/llm/provider", {
    method: "PUT",
  });
}

export async function POST(request: NextRequest) {
  return proxyToBackend(request, "/api/admin/llm/provider", {
    method: "POST",
  });
}
