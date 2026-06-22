import { fetchUserServiceSS } from "@/lib/utilsSS";
import { NextResponse } from "next/server";

export async function GET() {
  try {
    const response = await fetchUserServiceSS("/api/auth/type");
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
