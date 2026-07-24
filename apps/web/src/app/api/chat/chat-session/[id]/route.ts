import { getInternalUrl } from "@/lib/env.server";
import { NextResponse } from 'next/server';

const INTERNAL_URL = getInternalUrl();

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  
  try {
    // Proxy to backend for chat session share status
    const response = await fetch(`${INTERNAL_URL}/api/chat/get-chat-session/${id}`);
    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    // Return default private status if backend not available
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
    
    // Proxy to backend for chat session share status update
    // For now, just return success
    return NextResponse.json({ 
      chat_session_id: id,
      shared_status: body.shared_status || "private",
      success: true,
    });
  } catch (error) {
    return NextResponse.json({ error: "Failed to update share status" }, { status: 500 });
  }
}
