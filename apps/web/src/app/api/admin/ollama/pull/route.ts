import { getInternalUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { NextRequest, NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };
    const cookie = request.headers.get("cookie");
    if (cookie) {
      headers["Cookie"] = cookie;
    }
    const upstream = await fetch(
      buildServiceUrl(
        INTERNAL_URL,
        "agent",
        "/api/admin/ollama/pull"
      ).toString(),
      {
        method: "POST",
        body,
        headers,
      }
    );

    if (!upstream.body) {
      return NextResponse.json({ error: "No body" }, { status: 500 });
    }

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "text/event-stream" },
    });
  } catch {
    return NextResponse.json({ error: "Failed" }, { status: 500 });
  }
}
