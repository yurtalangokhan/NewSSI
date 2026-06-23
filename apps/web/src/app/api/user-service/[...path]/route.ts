import { NextRequest } from "next/server";

import { proxyToBackend } from "@/lib/api/proxy";
import { USER_SERVICE_URL } from "@/lib/constants";

// Preserve trailing slash from the original URL to avoid FastAPI 307 redirect
function buildUserServicePath(path: string[], request: NextRequest) {
  let result = `/api/${path.join("/")}`;
  if (request.nextUrl.pathname.endsWith("/") && !result.endsWith("/")) {
    result += "/";
  }
  return result;
}

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
