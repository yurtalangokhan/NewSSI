import { NextRequest, NextResponse } from "next/server";

const INTERNAL_URL = process.env.INTERNAL_URL || "http://localhost:8123";

async function proxyPersonaById(
  request: NextRequest,
  personaId: string
): Promise<NextResponse> {
  try {
    const url = new URL(request.url);
    const targetUrl = new URL(`${INTERNAL_URL}/api/persona/${personaId}`);

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
    console.error("Persona by-id proxy error:", error);
    return NextResponse.json(
      { error: "Failed to proxy persona request" },
      { status: 500 }
    );
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ personaId: string }> }
) {
  const { personaId } = await params;
  return proxyPersonaById(request, personaId);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ personaId: string }> }
) {
  const { personaId } = await params;
  return proxyPersonaById(request, personaId);
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ personaId: string }> }
) {
  const { personaId } = await params;
  return proxyPersonaById(request, personaId);
}
