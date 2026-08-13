import { getInternalUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { getLanguageHeaders } from "@/lib/api/proxy";
import { NextRequest, NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

export async function GET(request: NextRequest) {
  try {
    const headers: HeadersInit = { ...getLanguageHeaders(request) };
    const cookie = request.headers.get("cookie");
    const authorization = request.headers.get("authorization");
    if (cookie) {
      headers["Cookie"] = cookie;
    }
    if (authorization) {
      headers["Authorization"] = authorization;
    }

    const response = await fetch(
      buildServiceUrl(INTERNAL_URL, "agent", "/mcp/tools-builtin").toString(),
      {
        cache: "no-store",
        headers,
      }
    );

    if (!response.ok) {
      return NextResponse.json([]);
    }

    const data = await response.json();
    return NextResponse.json(Array.isArray(data?.tools) ? data.tools : []);
  } catch {
    return NextResponse.json([]);
  }
}
