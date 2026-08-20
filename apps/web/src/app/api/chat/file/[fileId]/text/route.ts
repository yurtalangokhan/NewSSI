import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ fileId: string }> }
) {
  const { fileId } = await params;
  return proxyToBackend(
    request,
    `/api/chat/file/${encodeURIComponent(fileId)}/text`,
    {
      backendService: "agent",
    }
  );
}
