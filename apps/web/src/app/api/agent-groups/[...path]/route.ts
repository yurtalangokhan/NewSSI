import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

function agentGroupsPath(path: string[]) {
  const suffix = path.join("/");
  return `/api/agent-groups${suffix ? `/${suffix}` : ""}`;
}

export async function GET(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(request, agentGroupsPath((await props.params).path));
}

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(request, agentGroupsPath((await props.params).path), {
    method: "PATCH",
  });
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToBackend(request, agentGroupsPath((await props.params).path), {
    method: "DELETE",
  });
}
