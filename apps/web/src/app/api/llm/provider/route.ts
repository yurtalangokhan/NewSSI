import { getInternalUrl } from "@/lib/env.server";
import { NextResponse } from 'next/server';

const INTERNAL_URL = getInternalUrl();

export async function GET() {
  try {
    const response = await fetch(`${INTERNAL_URL}/admin/llm/provider`);
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ providers: [], selected_provider: null });
  }
}
