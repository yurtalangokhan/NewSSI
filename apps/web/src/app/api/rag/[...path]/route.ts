import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/api/proxy";
import { getRagServiceUrl } from "@/lib/env.server";

// LANGCONNECT_URL is the canonical env var for the RAG service (see configs/.env)
const LANGCONNECT_URL = getRagServiceUrl();
type ProxyMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

/**
 * Proxy to LangConnect RAG service.
 * Handles all HTTP methods including multipart/form-data file uploads.
 *
 * Maps /api/rag/<rest> → <RAG_SERVICE_URL>/<rest>
 *
 * IMPORTANT: Do NOT override Content-Type for POST requests —
 * multipart/form-data requires the browser-set boundary to pass through.
 */
async function proxyToRagService(
  request: NextRequest,
  path: string[],
  method: ProxyMethod
): Promise<NextResponse> {
  return proxyToBackend(request, `/${path.join("/")}`, {
    method,
    backendUrl: LANGCONNECT_URL,
    backendService: "rag",
  });
}

export async function GET(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToRagService(request, (await props.params).path, "GET");
}

export async function POST(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToRagService(request, (await props.params).path, "POST");
}

export async function PUT(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToRagService(request, (await props.params).path, "PUT");
}

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToRagService(request, (await props.params).path, "PATCH");
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToRagService(request, (await props.params).path, "DELETE");
}
