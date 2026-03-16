import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    auto_scroll: true,
    application_status: "active",
    gpu_enabled: false,
    maximum_chat_retention_days: null,
    notifications: [],
    needs_reindexing: false,
    anonymous_user_enabled: true,
    invite_only_enabled: false,
    deep_research_enabled: true,
    temperature_override_enabled: true,
    query_history_type: "normal",
  });
}
