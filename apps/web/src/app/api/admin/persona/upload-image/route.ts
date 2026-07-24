import { getInternalUrl } from "@/lib/env.server";
import { NextResponse } from 'next/server';

const INTERNAL_URL = getInternalUrl();

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const response = await fetch(`${INTERNAL_URL}/api/admin/persona/upload-image`, {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: "Failed to upload image" }, { status: 500 });
  }
}
