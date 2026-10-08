import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { proxyToBackend } from "@/lib/api/proxy";

import { NextRequest } from "next/server";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ fileId: string }> }
) {
  const { fileId } = await params;
  return proxyToBackend(request, chatEndpoints.file(fileId).backend);
}
