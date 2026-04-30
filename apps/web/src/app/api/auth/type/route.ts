import { fetchSS } from "@/lib/utilsSS";
import { NextResponse } from "next/server";

export async function GET() {
  try {
    const response = await fetchSS("/auth/type");
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json(
      {
        authType: "basic",
        autoRedirect: false,
        requiresVerification: false,
        anonymousUserEnabled: true,
        passwordMinLength: 8,
        hasUsers: true,
        oauthEnabled: false,
      },
      { status: 200 }
    );
  }
}
