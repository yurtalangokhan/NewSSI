import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  return proxyToBackend(request, `/api/admin/user-providers/${id}`, {
    method: "PUT",
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  return proxyToBackend(request, `/api/admin/user-providers/${id}`, {
    method: "DELETE",
  });
}
