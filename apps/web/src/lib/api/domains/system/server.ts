import { systemEndpoints } from "@/lib/api/domains/system/endpoints";
import { backendRequest } from "@/lib/api/http/server";
import { getServerRequestHeaders } from "@/lib/api/server-context";

import type { BackendTarget } from "@/lib/api/http/types";

async function requestSystemTarget(target: BackendTarget): Promise<Response> {
  return backendRequest({
    ...target,
    credentials: "include",
    cache: "no-store",
    headers: await getServerRequestHeaders(),
  });
}

export function fetchEnterpriseSettingsSS(): Promise<Response> {
  return requestSystemTarget(systemEndpoints.getEnterpriseSettings.backend);
}

export function fetchCustomAnalyticsScriptSS(): Promise<Response> {
  return requestSystemTarget(systemEndpoints.getCustomAnalyticsScript.backend);
}

export function fetchWebVersionSS(): Promise<Response> {
  return requestSystemTarget(systemEndpoints.version.backend);
}
