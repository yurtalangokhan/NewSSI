import { NextResponse } from "next/server";

import { internalServerErrorResponse } from "@/lib/api/errorResponse";

export async function GET(request: Request) {
  try {
    // For now, return empty search results
    // In production, this would search through chat sessions and messages
    return NextResponse.json({
      groups: [],
      has_more: false,
      next_page: null,
    });
  } catch (error) {
    return internalServerErrorResponse("Search failed");
  }
}
