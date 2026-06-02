import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ chatSessionId: string }> }
) {
  const { chatSessionId } = await params;
  return proxyToBackend(
    request,
    `/api/chat/delete-chat-session/${chatSessionId}`,
    {
      method: "DELETE",
    }
  );
}

// Also support POST for backward compatibility
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ chatSessionId: string }> }
) {
  return DELETE(request, { params });
}
