import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const query = searchParams.get('query');
    
    // For now, return empty search results
    // In production, this would search through chat sessions and messages
    return NextResponse.json({
      results: [],
      query: query,
      total: 0,
    });
  } catch (error) {
    return NextResponse.json({ error: "Search failed" }, { status: 500 });
  }
}
