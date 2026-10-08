"use client";

import { useCallback, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  buildMermaidFixRequest,
  type MermaidDiagnostic,
} from "@/components/mermaid/mermaidDiagnostics";

interface FollowUpSubmit {
  message: string;
  currentMessageFiles: never[];
  deepResearch: boolean;
}

/**
 * "Ask the agent to fix" for diagrams inside the panel. The composer has no
 * prefill API, so this is an ordinary send (as in Plan 2's chat variant);
 * `useChatController` attaches `document_context` while the panel is open.
 *
 * The returned callback keeps one identity for the component's lifetime: the
 * send handler changes on every streamed packet, and a new identity would
 * recreate the markdown code renderer and remount every diagram.
 */
export function usePanelMermaidFix(
  onSubmit: (props: FollowUpSubmit) => void,
  deepResearch: boolean
) {
  const { t } = useTranslation();
  const latest = useRef({ onSubmit, deepResearch, t });
  useEffect(() => {
    latest.current = { onSubmit, deepResearch, t };
  }, [onSubmit, deepResearch, t]);

  return useCallback((source: string, diagnostic: MermaidDiagnostic) => {
    const current = latest.current;
    current.onSubmit({
      message: buildMermaidFixRequest(current.t, source, diagnostic),
      currentMessageFiles: [],
      deepResearch: current.deepResearch,
    });
  }, []);
}
