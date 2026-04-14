import { NextRequest, NextResponse } from "next/server";

const AGENT_SERVICE_URL =
  process.env.AGENT_SERVICE_URL ||
  process.env.INTERNAL_URL ||
  "http://localhost:8123";

/**
 * Generic proxy to agent-service for all HTTP methods.
 * Maps /api/agent/<rest> → <AGENT_SERVICE_URL>/<rest>
 */
async function proxyToAgentService(
  request: NextRequest,
  path: string[]
): Promise<NextResponse> {
  try {
    const url = new URL(request.url);
    const targetPath = path.join("/");
    const targetUrl = new URL(`${AGENT_SERVICE_URL}/${targetPath}`);

    url.searchParams.forEach((value, key) => {
      targetUrl.searchParams.append(key, value);
    });

    const response = await fetch(targetUrl.toString(), {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
      },
      body:
        request.method !== "GET" && request.method !== "HEAD"
          ? await request.text()
          : undefined,
    });

    const data = await response.json().catch(() => null);

    return NextResponse.json(data ?? {}, { status: response.status });
  } catch (error) {
    console.error("Agent service proxy error:", error);
    return NextResponse.json(
      { error: "Agent service proxy error" },
      { status: 500 }
    );
  }
}

export async function GET(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToAgentService(request, (await props.params).path);
}

export async function POST(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToAgentService(request, (await props.params).path);
}

export async function PUT(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToAgentService(request, (await props.params).path);
}

export async function PATCH(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToAgentService(request, (await props.params).path);
}

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ path: string[] }> }
) {
  return proxyToAgentService(request, (await props.params).path);
}
