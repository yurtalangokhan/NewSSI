import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    authType: "basic",
    autoRedirect: false,
    requiresVerification: false,
    anonymousUserEnabled: true,
    passwordMinLength: 8,
    hasUsers: true,
    oauthEnabled: false,
  });
}
