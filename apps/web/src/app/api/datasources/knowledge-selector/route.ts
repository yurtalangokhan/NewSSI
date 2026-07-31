import { NextRequest, NextResponse } from "next/server";
import { proxyToBackend } from "@/lib/api/proxy";
import { getRagServiceUrl } from "@/lib/env.server";

const LANGCONNECT_URL = getRagServiceUrl();

export async function GET(request: NextRequest) {
  try {
    const response = await proxyToBackend(request, "/datasources/knowledge-selector", {
      backendUrl: LANGCONNECT_URL,
      backendService: "rag",
      refreshOnUnauthorized: false,
    });
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch (error) {
    const response = NextResponse.json(
      { document_processing: [], knowledge_graph: [] },
      { status: 500 }
    );
    response.headers.set("Cache-Control", "no-store");
    return response;
  }
}
