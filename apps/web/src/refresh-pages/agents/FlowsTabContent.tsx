"use client";

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import FlowCard from "@/sections/cards/FlowCard";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { AgentsGridSkeleton } from "@/refresh-components/skeletons/AgentCardSkeleton";
import { isFlowAgent } from "@/lib/flows/flowAgent";
import CreatorFilterPopover, { creatorFilterId } from "./CreatorFilterPopover";

export interface FlowsTabContentProps {
  agents: MinimalPersonaSnapshot[];
  isLoading: boolean;
}

export default function FlowsTabContent({
  agents,
  isLoading,
}: FlowsTabContentProps) {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCreatorIds, setSelectedCreatorIds] = useState<Set<string>>(
    new Set()
  );

  const allFlows = useMemo(() => agents.filter(isFlowAgent), [agents]);

  const flows = useMemo(
    () =>
      allFlows
        .filter((agent) =>
          agent.name.toLowerCase().includes(searchQuery.toLowerCase())
        )
        .filter((agent) => {
          const agentCreatorId = creatorFilterId(agent.owner);
          return (
            selectedCreatorIds.size === 0 ||
            (!!agentCreatorId && selectedCreatorIds.has(agentCreatorId))
          );
        }),
    [allFlows, searchQuery, selectedCreatorIds]
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
        <div className="flex-1 min-w-0">
          <InputTypeIn
            placeholder={t("flowsPage.searchFlowsPlaceholder")}
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            leftSearchIcon
          />
        </div>
        <div className="flex flex-row items-center gap-2 shrink-0">
          <CreatorFilterPopover
            agents={allFlows}
            selectedCreatorIds={selectedCreatorIds}
            setSelectedCreatorIds={setSelectedCreatorIds}
          />
        </div>
      </div>

      {isLoading ? (
        <AgentsGridSkeleton count={4} />
      ) : flows.length === 0 ? (
        <Text
          as="p"
          className="w-full h-full flex flex-col items-center justify-center py-12"
          text03
        >
          {t("flowsPage.noFlowsFound")}
        </Text>
      ) : (
        <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-2">
          {flows.map((flow) => (
            <FlowCard key={flow.id} agent={flow} />
          ))}
        </div>
      )}
    </div>
  );
}
