import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

function agentDefinitionsPath(path: string[]) {
  const suffix = path.join("/");
  return `/agent-definitions${suffix ? `/${suffix}` : ""}`;
}

export async function GET(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentDefinitionsPath((await props.params).path)
  );
}

export async function POST(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentDefinitionsPath((await props.params).path),
    { method: "POST" }
  );
}

export async function PUT(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentDefinitionsPath((await props.params).path),
    { method: "PUT" }
  );
}

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentDefinitionsPath((await props.params).path),
    { method: "PATCH" }
  );
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(
    request,
    agentDefinitionsPath((await props.params).path),
    { method: "DELETE" }
  );
}
