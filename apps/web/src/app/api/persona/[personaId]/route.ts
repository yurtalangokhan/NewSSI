import { agentsEndpoints } from "@/lib/api/domains/agents/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ personaId: string }> }
) {
  const { personaId } = await params;
  return proxyToBackend(request, agentsEndpoints.getPersona(personaId).backend);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ personaId: string }> }
) {
  const { personaId } = await params;
  return proxyToBackend(
    request,
    agentsEndpoints.updatePersona(personaId).backend,
    {
      method: "PATCH",
    }
  );
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ personaId: string }> }
) {
  const { personaId } = await params;
  return proxyToBackend(
    request,
    agentsEndpoints.deletePersona(personaId).backend,
    {
      method: "DELETE",
    }
  );
}
