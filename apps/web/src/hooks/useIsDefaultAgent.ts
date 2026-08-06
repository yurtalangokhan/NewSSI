"use client";

import { useMemo } from "react";
import { CombinedSettings } from "@/interfaces/settings";
import { ChatSession } from "@/app/app/interfaces";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { DEFAULT_AGENT_ID } from "@/lib/constants";
import useAppFocus from "@/hooks/useAppFocus";

/**
 * Determines if the current assistant is the default agent based on:
 * 1. Whether default agent is disabled in settings
 * 2. If URL has an agentId specified
 * 3. Based on the current chat session
 */
export default function useIsDefaultAgent({
  liveAgent,
  existingChatSessionId,
  selectedChatSession,
  settings,
}: {
  liveAgent: MinimalPersonaSnapshot | undefined;
  existingChatSessionId: string | null;
  selectedChatSession: ChatSession | undefined;
  settings: CombinedSettings | null;
}) {
  const appFocus = useAppFocus();
  const urlAssistantId = appFocus.isAgent() ? appFocus.getId() : null;

  return useMemo(() => {
    // If default agent is disabled, it can never be the default agent
    if (settings?.settings?.disable_default_assistant) {
      return false;
    }

    // If URL has an agentId, it's explicitly selected, not default
    if (
      urlAssistantId !== null &&
      urlAssistantId !== DEFAULT_AGENT_ID.toString()
    ) {
      return false;
    }

    // If there's an existing chat session with a persona_id, it's not default
    if (
      existingChatSessionId &&
      selectedChatSession?.persona_id !== DEFAULT_AGENT_ID
    ) {
      return false;
    }

    // If just on `/chat` page, it's the default agent
    return true;
  }, [
    settings?.settings?.disable_default_assistant,
    urlAssistantId,
    existingChatSessionId,
    selectedChatSession?.persona_id,
    liveAgent?.id,
  ]);
}
