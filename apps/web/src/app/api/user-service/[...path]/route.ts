import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/api/proxy";
import { buildUserServicePath } from "@/lib/api/userServicePath";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyToBackend(request, buildUserServicePath(path, request), {
    backendService: "user",
  });
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyToBackend(request, buildUserServicePath(path, request), {
    backendService: "user",
  });
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyToBackend(request, buildUserServicePath(path, request), {
    backendService: "user",
  });
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyToBackend(request, buildUserServicePath(path, request), {
    backendService: "user",
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyToBackend(request, buildUserServicePath(path, request), {
    backendService: "user",
  });
}
