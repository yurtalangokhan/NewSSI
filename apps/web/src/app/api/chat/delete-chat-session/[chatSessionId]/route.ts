import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ chatSessionId: string }> }
) {
  const { chatSessionId } = await params;
  return proxyToBackend(
    request,
    chatEndpoints.deleteSession(chatSessionId).backend,
    {
      method: "DELETE",
    }
  );
}
