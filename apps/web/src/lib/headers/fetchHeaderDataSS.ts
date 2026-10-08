import { CombinedSettings } from "@/interfaces/settings";
import { ChatSession, toChatSession } from "@/lib/api/domains/chat/types";
import { fetchSettingsSS } from "@/components/settings/lib";
import { fetchBackendChatSessionSS } from "@/lib/api/domains/chat/server";

export interface HeaderData {
  settings: CombinedSettings | null;
  chatSession: ChatSession | null;
}

export async function fetchHeaderDataSS(
  chatSessionId?: string
): Promise<HeaderData> {
  const [settings, backendChatSession] = await Promise.all([
    fetchSettingsSS(),
    chatSessionId
      ? fetchBackendChatSessionSS(chatSessionId)
      : Promise.resolve(null),
  ]);
  const chatSession = backendChatSession
    ? toChatSession(backendChatSession)
    : null;

  return {
    settings,
    chatSession,
  };
}
