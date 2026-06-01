"use client";

import React, { memo, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { usePinnedAgents, useCurrentAgent } from "@/hooks/useAgents";
import { useProjectsContext } from "@/providers/ProjectsContext";
import { cn, noProp } from "@/lib/utils";
import SidebarTab from "@/refresh-components/buttons/SidebarTab";
import IconButton from "@/refresh-components/buttons/IconButton";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import useOnMount from "@/hooks/useOnMount";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import { SvgPin, SvgX } from "@opal/icons";

interface SortableItemProps {
  id: number;
  children?: React.ReactNode;
}

function SortableItem({ id, children }: SortableItemProps) {
  const isMounted = useOnMount();
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useSortable({ id });

  if (!isMounted) {
    return <div className="flex items-center group">{children}</div>;
  }

  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        ...(isDragging && { zIndex: 1000, position: "relative" as const }),
      }}
      {...attributes}
      {...listeners}
      className="flex items-center group"
    >
      {children}
    </div>
  );
}

export interface AgentButtonProps {
  agent: MinimalPersonaSnapshot;
}

const AgentButton = memo(({ agent }: AgentButtonProps) => {
  const currentAgent = useCurrentAgent();
  const { pinnedAgents, togglePinnedAgent } = usePinnedAgents();
  const { currentProjectId } = useProjectsContext();
  const { t } = useTranslation();
  const routeAgentId = agent.external_id ?? agent.id;
  const isActuallyPinned = pinnedAgents.some((a) => a.id === agent.id);
  const isCurrentAgent = currentAgent?.id === agent.id;
  const href = useMemo(() => {
    const params = new URLSearchParams({ agentId: String(routeAgentId) });
    if (currentProjectId) {
      params.set("projectId", String(currentProjectId));
    }
    return `/app?${params.toString()}`;
  }, [routeAgentId, currentProjectId]);

  const handleClick = async () => {
    if (!isActuallyPinned) {
      await togglePinnedAgent(agent, true);
    }
  };

  return (
    <SortableItem id={agent.id}>
      <div className="flex flex-col w-full h-full">
        <SidebarTab
          key={agent.id}
          leftIcon={() => <AgentAvatar agent={agent} />}
          href={href}
          onClick={handleClick}
          transient={isCurrentAgent}
          rightChildren={
            // Hide unpin button for current agent since auto-pin would immediately re-pin
            isCurrentAgent ? null : (
              <IconButton
                icon={
                  SvgX /* We only show the unpin button for pinned agents */
                }
                internal
                onClick={noProp(() => togglePinnedAgent(agent, false))}
                className={cn("hidden group-hover/SidebarTab:flex")}
                tooltip={t("sidebar.unpinAgent")}
              />
            )
          }
        >
          {agent.name}
        </SidebarTab>
      </div>
    </SortableItem>
  );
});
AgentButton.displayName = "AgentButton";

export default AgentButton;
