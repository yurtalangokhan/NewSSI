import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    id: "dev-user",
    email: "dev@local.dev",
    is_active: true,
    is_superuser: true,
    is_verified: true,
    role: "admin",
    preferences: {
      chosen_assistants: null,
      visible_assistants: [],
      hidden_assistants: [],
      default_model: null,
      recent_assistants: [],
      auto_scroll: true,
      shortcut_enabled: true,
      temperature_override_enabled: false,
      theme_preference: null,
      chat_background: null,
      default_app_mode: "CHAT",
    },
    team_name: null,
    is_anonymous_user: false,
    password_configured: true,
  });
}
