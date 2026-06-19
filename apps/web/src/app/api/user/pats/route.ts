import { USER_SERVICE_URL } from "@/lib/constants";
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Cookie: request.headers.get("cookie") || "",
  };
  const auth = request.headers.get("authorization");
  if (auth) headers["Authorization"] = auth;

  const response = await fetch(`${USER_SERVICE_URL}/api/users/me/api-keys/`, {
    headers,
  });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Cookie: request.headers.get("cookie") || "",
  };
  const auth = request.headers.get("authorization");
  if (auth) headers["Authorization"] = auth;

  const response = await fetch(`${USER_SERVICE_URL}/api/users/me/api-keys/`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
