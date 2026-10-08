import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { forwardBackendResponse } from "@/lib/api/backendResponse";
import { NextRequest } from "next/server";
import { appSettings } from "@/lib/settings";

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ patId: string }> }
) {
  const params = await props.params;
  const response = await backendRequest({
    ...sessionEndpoints.deletePersonalAccessToken(params.patId).backend,
    request,
    method: "DELETE",
  });
  return forwardBackendResponse(response);
}
