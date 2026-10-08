import { datasourcesEndpoints } from "@/lib/api/domains/datasources/endpoints";
import { NextRequest, NextResponse } from "next/server";

import { proxyToBackend } from "@/lib/api/proxy";

export async function GET(request: NextRequest) {
  try {
    const response = await proxyToBackend(
      request,
      datasourcesEndpoints.getKnowledgeSelector().backend
    );
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
