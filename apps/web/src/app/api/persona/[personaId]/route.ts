import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ personaId: string }> }
) {
  const { personaId } = await params;
  return proxyToBackend(request, `/api/persona/${personaId}`);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ personaId: string }> }
) {
  const { personaId } = await params;
  return proxyToBackend(request, `/api/persona/${personaId}`, {
    method: "PATCH",
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ personaId: string }> }
) {
  const { personaId } = await params;
  return proxyToBackend(request, `/api/persona/${personaId}`, {
    method: "DELETE",
  });
}
