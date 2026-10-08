import { toolsEndpoints } from "@/lib/api/domains/tools/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  try {
    const response = await backendRequest({
      request,
      ...toolsEndpoints.listBuiltInTools.backend,
      cache: "no-store",
      deriveAuthorizationFromCookie: true,
    });
    if (!response.ok) throw new Error("Backend request failed");
    const data = (await response.json()) as { tools?: unknown[] };
    return NextResponse.json(Array.isArray(data?.tools) ? data.tools : []);
  } catch (error) {
    console.warn("[api/tool/openapi] GET handler threw", error);
    return NextResponse.json([]);
  }
}
