import { NextRequest, NextResponse } from "next/server";

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

async function proxyToAgentDefinitions(request: NextRequest): Promise<NextResponse> {
  try {
    const url = new URL(request.url);
    const targetUrl = new URL(`${INTERNAL_URL}/agent-definitions`);

    url.searchParams.forEach((value, key) => {
      targetUrl.searchParams.append(key, value);
    });

    const hasBody = request.method !== "GET" && request.method !== "HEAD";
    const forwardedHeaders = new Headers(request.headers);
    forwardedHeaders.delete("host");

    const response = await fetch(targetUrl.toString(), {
      method: request.method,
      headers: forwardedHeaders,
      ...(hasBody ? ({ body: request.body, duplex: "half" } as RequestInit) : {}),
    });

    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
    }

    return new NextResponse(response.body, {
      status: response.status,
      headers: new Headers(response.headers),
    });
  } catch (error) {
    console.error("Agent definitions root proxy error:", error);
    return NextResponse.json(
      { error: "Agent definitions proxy error" },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest) {
  return proxyToAgentDefinitions(request);
}

export async function POST(request: NextRequest) {
  return proxyToAgentDefinitions(request);
}