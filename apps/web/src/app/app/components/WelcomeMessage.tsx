"use client";

import Logo from "@/refresh-components/Logo";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import Text from "@/refresh-components/texts/Text";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { useState, useEffect, useMemo } from "react";
import { useSettingsContext } from "@/providers/SettingsProvider";
import FrostedDiv from "@/refresh-components/FrostedDiv";
import { useTranslation } from "react-i18next";

export interface WelcomeMessageProps {
  agent?: MinimalPersonaSnapshot;
  isDefaultAgent: boolean;
}

export default function WelcomeMessage({
  agent,
  isDefaultAgent,
}: WelcomeMessageProps) {
  const { t } = useTranslation();
  const settings = useSettingsContext();
  const enterpriseSettings = settings?.enterpriseSettings;
  const greetings = useMemo(
    () => [t("app.greetings.howCanIHelp"), t("app.greetings.letsGetStarted")],
    [t]
  );

  // Use a stable default for SSR, then randomize on client after hydration
  const [greeting, setGreeting] = useState(greetings[0]);

  useEffect(() => {
    if (enterpriseSettings?.custom_greeting_message) {
      setGreeting(enterpriseSettings.custom_greeting_message);
    } else {
      setGreeting(greetings[Math.floor(Math.random() * greetings.length)]);
    }
  }, [enterpriseSettings?.custom_greeting_message, greetings]);

  let content: React.ReactNode = null;

  if (isDefaultAgent) {
    content = (
      <div data-testid="onyx-logo" className="flex flex-row items-center gap-4">
        <Logo folded size={32} />
        <Text as="p" headingH2>
          {greeting}
        </Text>
      </div>
    );
  } else if (agent) {
    content = (
      <>
        <div
          data-testid="agent-name-display"
          className="flex flex-row items-center gap-3"
        >
          <AgentAvatar agent={agent} size={36} />
          <Text as="p" headingH2>
            {agent.name}
          </Text>
        </div>
      </>
    );
  }

  // if we aren't using the default agent, we need to wait for the agent info to load
  // before rendering
  if (!content) return null;

  return (
    <FrostedDiv
      data-testid="chat-intro"
      className="flex flex-col items-center justify-center gap-3 w-full max-w-[var(--app-page-main-content-width)]"
    >
      {content}
    </FrostedDiv>
  );
}
