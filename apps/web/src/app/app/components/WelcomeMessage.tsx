"use client";

import Logo from "@/refresh-components/Logo";
import { GREETING_KEYS } from "@/lib/chat/greetingMessages";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import Text from "@/refresh-components/texts/Text";
import { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";
import { useState, useEffect } from "react";
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

  // Keep initial render deterministic in the active locale.
  // Randomized greeting is selected after hydration on client.
  const [greeting, setGreeting] = useState(() =>
    t("app.greetings." + GREETING_KEYS[0])
  );

  useEffect(() => {
    if (enterpriseSettings?.custom_greeting_message) {
      setGreeting(enterpriseSettings.custom_greeting_message);
    } else {
      const localizedGreetings = GREETING_KEYS.map((key) =>
        t("app.greetings." + key)
      );

      const randomGreeting =
        localizedGreetings[
          Math.floor(Math.random() * localizedGreetings.length)
        ];
      if (randomGreeting) {
        setGreeting(randomGreeting);
      }
    }
  }, [enterpriseSettings?.custom_greeting_message, t]);

  let content: React.ReactNode = null;

  if (isDefaultAgent) {
    content = (
      <div
        data-testid="atlas-logo"
        className="flex flex-row items-center gap-4"
      >
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
