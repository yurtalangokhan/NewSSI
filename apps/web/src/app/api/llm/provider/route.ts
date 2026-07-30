import { getInternalUrl } from "@/lib/env.server";
import { buildServiceUrl } from "@/lib/api/gatewayRouting";
import { NextResponse } from "next/server";

const INTERNAL_URL = getInternalUrl();

export async function GET() {
  try {
    const response = await fetch(
      buildServiceUrl(INTERNAL_URL, "agent", "/admin/llm/provider").toString()
    );
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ providers: [], selected_provider: null });
  }
}
