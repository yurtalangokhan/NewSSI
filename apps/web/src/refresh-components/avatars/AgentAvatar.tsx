"use client";

import { useTranslation } from "react-i18next";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { buildImgUrl } from "@/app/app/components/files/images/utils";
import {
  DEFAULT_AGENT_AVATAR_SIZE_PX,
  DEFAULT_AGENT_ID,
} from "@/lib/constants";
import CustomAgentAvatar from "@/refresh-components/avatars/CustomAgentAvatar";

export interface AgentAvatarProps {
  agent: MinimalPersonaSnapshot;
  size?: number;
}

export default function AgentAvatar({
  agent,
  size = DEFAULT_AGENT_AVATAR_SIZE_PX,
  ...props
}: AgentAvatarProps) {
  const { t } = useTranslation("common", { keyPrefix: "common" });
  if (agent.id === DEFAULT_AGENT_ID) {
    return (
      <img
        src="/logo.single.svg"
        alt={t("agentLogoAlt")}
        className="shrink-0"
        style={{ width: size, height: size }}
        draggable={false}
      />
    );
  }

  return (
    <CustomAgentAvatar
      name={agent.name}
      src={
        agent.uploaded_image_id
          ? buildImgUrl(agent.uploaded_image_id)
          : undefined
      }
      iconName={agent.icon_name}
      size={size}
      variant={agent.graph_schema === "flow" ? "flow" : "agent"}
      {...props}
    />
  );
}
