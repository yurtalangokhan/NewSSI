import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ chatSessionId: string }> }
) {
  const { chatSessionId } = await params;
  return proxyToBackend(request, `/api/chat/get-chat-session/${chatSessionId}`);
}
