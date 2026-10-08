import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { backendRequest } from "@/lib/api/http/server";

import { NextResponse } from "next/server";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  try {
    const response = await backendRequest({
      ...chatEndpoints.shareSession(id).backend,
    });
    if (!response.ok) throw new Error("Backend request failed");
    const data = (await response.json()) as {
      chat_session_id: string;
      shared_status: string;
    };
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({
      chat_session_id: id,
      shared_status: "private",
    });
  }
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  try {
    const body = await request.json();
    return NextResponse.json({
      chat_session_id: id,
      shared_status: body.shared_status || "private",
      success: true,
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to update share status" },
      { status: 500 }
    );
  }
}
