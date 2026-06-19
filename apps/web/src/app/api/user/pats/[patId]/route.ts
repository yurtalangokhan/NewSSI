import { USER_SERVICE_URL } from "@/lib/constants";
import { NextRequest, NextResponse } from "next/server";

export async function DELETE(
  request: NextRequest,
  props: { params: Promise<{ patId: string }> }
) {
  const params = await props.params;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Cookie: request.headers.get("cookie") || "",
  };
  const auth = request.headers.get("authorization");
  if (auth) headers["Authorization"] = auth;

  const response = await fetch(
    `${USER_SERVICE_URL}/api/users/me/api-keys/${params.patId}`,
    {
      method: "DELETE",
      headers,
    }
  );

  if (response.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
