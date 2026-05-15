import { proxyToBackend } from "@/lib/api/proxy";
import { NextRequest } from "next/server";

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ promptId: string }> }
) {
  const params = await props.params;
  return proxyToBackend(request, `/api/input_prompt/${params.promptId}`, {
    method: "PATCH",
    withCredentials: true,
  });
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ promptId: string }> }
) {
  const params = await props.params;
  return proxyToBackend(request, `/api/input_prompt/${params.promptId}`, {
    method: "DELETE",
    withCredentials: true,
  });
}
