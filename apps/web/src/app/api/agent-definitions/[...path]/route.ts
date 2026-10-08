import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentsEndpoints.definitions((await props.params).path).backend
  );
}

export async function POST(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentsEndpoints.definitions((await props.params).path).backend,
    { method: "POST" }
  );
}

export async function PUT(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentsEndpoints.definitions((await props.params).path).backend,
    { method: "PUT" }
  );
}

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentsEndpoints.definitions((await props.params).path).backend,
    { method: "PATCH" }
  );
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentsEndpoints.definitions((await props.params).path).backend,
    { method: "DELETE" }
  );
}
