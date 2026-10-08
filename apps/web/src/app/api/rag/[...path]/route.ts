import { knowledgeEndpoints } from "@/lib/api/domains/knowledge/endpoints";
import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/api/proxy";

type ProxyMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

/**
 * Proxy to the RAG service.
 * Handles all HTTP methods including multipart/form-data file uploads.
 *
 * Maps /api/rag/<rest> through the domain endpoint to the configured service.
 *
 * IMPORTANT: Do NOT override Content-Type for POST requests —
 * multipart/form-data requires the browser-set boundary to pass through.
 */
async function proxyToRagService(
  request: NextRequest,
  path: string[],
  method: ProxyMethod
): Promise<NextResponse> {
  return proxyToBackend(
    request,
    knowledgeEndpoints.ragProxyTarget(path).backend,
    {
      method,
    }
  );
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
