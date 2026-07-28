import { getInternalUrl } from "@/lib/env.server";
import { NextResponse } from 'next/server';

const INTERNAL_URL = getInternalUrl();

export async function GET() {
  try {
    const response = await fetch(`${INTERNAL_URL}/mcp/tools-builtin`, {
      cache: 'no-store',
    });

    if (!response.ok) {
      return NextResponse.json([]);
    }

    const data = await response.json();
    return NextResponse.json(Array.isArray(data?.tools) ? data.tools : []);
  } catch {
    return NextResponse.json([]);
  }
}
