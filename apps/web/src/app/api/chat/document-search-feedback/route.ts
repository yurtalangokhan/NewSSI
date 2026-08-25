import { NextResponse } from "next/server";

import { internalServerErrorResponse } from "@/lib/api/errorResponse";

export async function POST(request: Request) {
  try {
    const body = await request.json();

    // Proxy document search feedback to backend
    // For now, return success
    return NextResponse.json({
      success: true,
      feedback: body,
    });
  } catch (error) {
    return internalServerErrorResponse("Failed to submit feedback");
  }
}
