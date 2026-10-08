import { preferencesEndpoints } from "@/lib/api/domains/preferences/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextRequest } from "next/server";
import { appSettings } from "@/lib/settings";

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ promptId: string }> }
) {
  const params = await props.params;
  const body = await request.json();
  const response = await backendRequest({
    ...preferencesEndpoints.updateInputPrompt(params.promptId).backend,
    request,
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return forwardBackendResponse(response);
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ promptId: string }> }
) {
  const params = await props.params;
  const response = await backendRequest({
    ...preferencesEndpoints.deleteInputPrompt(params.promptId).backend,
    request,
    method: "DELETE",
  });
  return forwardBackendResponse(response);
}
