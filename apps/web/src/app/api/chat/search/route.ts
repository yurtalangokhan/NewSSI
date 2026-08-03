import { NextResponse } from "next/server";

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
    return NextResponse.json({ error: "Search failed" }, { status: 500 });
  }
}
