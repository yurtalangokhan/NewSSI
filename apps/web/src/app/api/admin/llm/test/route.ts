import { getInternalUrl } from "@/lib/env.server";
import { NextResponse } from 'next/server';

const INTERNAL_URL = getInternalUrl();

export async function POST() {
  try {
    const response = await fetch(`${INTERNAL_URL}/api/admin/llm/test`, { method: "POST" });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: "Failed" }, { status: 500 });
  }
}
