import { fetchAuthTypeResponseSS } from "@/lib/api/domains/session/server";
import { NextResponse } from "next/server";

export async function GET() {
  try {
    const response = await fetchAuthTypeResponseSS();
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json(
      {
        authType: "basic",
        autoRedirect: false,
        requiresVerification: false,
        anonymousUserEnabled: true,
        hasUsers: true,
        oauthEnabled: false,
        externalKeycloak: false,
        external_keycloak: false,
      },
      { status: 200 }
    );
  }
}
