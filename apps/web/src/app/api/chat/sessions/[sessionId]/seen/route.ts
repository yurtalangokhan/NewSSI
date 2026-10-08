import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  const { sessionId } = await params;
  return proxyToBackend(request, chatEndpoints.markSeen(sessionId).backend, {
    method: "POST",
  });
}
