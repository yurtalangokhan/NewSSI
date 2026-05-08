import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, "/api/input_prompt", {
    method: "GET",
    withCredentials: true,
  });
}

export async function POST(request: NextRequest) {
  return proxyToBackend(request, "/api/input_prompt", {
    method: "POST",
    withCredentials: true,
  });
}
