import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  return proxyToBackend(request, `/api/admin/providers/${id}/sync-models`, {
    method: "POST",
  });
}
