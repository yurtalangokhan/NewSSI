import { modelProvidersEndpoints } from "@/lib/api/domains/model-providers/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { NextResponse } from "next/server";

export async function GET() {
  try {
    const response = await backendRequest({
      ...modelProvidersEndpoints.getProviderSelection.backend,
    });
    if (!response.ok) throw new Error("Backend request failed");
    const data = (await response.json()) as {
      providers: unknown[];
      selected_provider: unknown;
    };
    return NextResponse.json(
      data ?? { providers: [], selected_provider: null }
    );
  } catch (error) {
    return NextResponse.json({ providers: [], selected_provider: null });
  }
}
