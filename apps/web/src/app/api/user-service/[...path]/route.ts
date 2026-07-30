import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/api/proxy";
import { USER_SERVICE_URL } from "@/lib/constants";
import { buildUserServicePath } from "@/lib/api/userServicePath";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyToBackend(request, buildUserServicePath(path, request), {
    backendUrl: USER_SERVICE_URL,
  });
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyToBackend(request, buildUserServicePath(path, request), {
    backendUrl: USER_SERVICE_URL,
  });
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyToBackend(request, buildUserServicePath(path, request), {
    backendUrl: USER_SERVICE_URL,
  });
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyToBackend(request, buildUserServicePath(path, request), {
    backendUrl: USER_SERVICE_URL,
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxyToBackend(request, buildUserServicePath(path, request), {
    backendUrl: USER_SERVICE_URL,
  });
}
