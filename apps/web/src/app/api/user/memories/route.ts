import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  return proxyToBackend(request, "/api/user/memories", {
    method: "GET",
    withCredentials: true,
  });
}

export async function POST(request: NextRequest) {
  return proxyToBackend(request, "/api/user/memories", {
    method: "POST",
    withCredentials: true,
  });
}

export async function DELETE(request: NextRequest) {
  return proxyToBackend(request, "/api/user/memories", {
    method: "DELETE",
    withCredentials: true,
  });
}
