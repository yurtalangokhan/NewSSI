"use client";

import { useMemo, useState, useRef } from "react";
import AgentCard from "@/sections/cards/AgentCard";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { isFlowAgent } from "@/lib/flows/flowAgent";
import Text from "@/refresh-components/texts/Text";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import TextSeparator from "@/refresh-components/TextSeparator";
import { AgentsGridSkeleton } from "@/refresh-components/skeletons/AgentCardSkeleton";
import FilterButton from "@/refresh-components/buttons/FilterButton";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import LineItem from "@/refresh-components/buttons/LineItem";
import {
  SEARCH_TOOL_ID,
  IMAGE_GENERATION_TOOL_ID,
  OPEN_URL_TOOL_ID,
  OPEN_URL_TOOL_NAME,
  WEB_SEARCH_TOOL_ID,
  SYSTEM_TOOL_ICONS,
} from "@/app/app/components/tools/constants";
import { SvgActions } from "@opal/icons";
import useOnMount from "@/hooks/useOnMount";
import { useTranslation } from "react-i18next";
import CreatorFilterPopover, { creatorFilterId } from "./CreatorFilterPopover";

interface AgentsSectionProps {
  title: string;
  description?: string;
  agents: MinimalPersonaSnapshot[];
}

function AgentsSection({ title, description, agents }: AgentsSectionProps) {
  if (agents.length === 0) return null;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Text as="p" headingH3>
          {title}
        </Text>
        <Text as="p" secondaryBody text03>
          {description}
        </Text>
      </div>
      <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-2">
        {agents
          .sort((a, b) => {
            if (typeof a.id === "number" && typeof b.id === "number") {
              return b.id - a.id;
            }
            return String(b.id).localeCompare(String(a.id));
          })
          .map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
      </div>
    </div>
  );
}

export interface AgentsTabContentProps {
  agents: MinimalPersonaSnapshot[];
  isLoading: boolean;
}

/** The agents half of the page: search, creator/actions filters,
 * and Featured/All sections — flows filtered out. */
export default function AgentsTabContent({
  agents: allAgentsAndFlows,
  isLoading,
}: AgentsTabContentProps) {
  const [actionsFilterOpen, setActionsFilterOpen] = useState(false);
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCreatorIds, setSelectedCreatorIds] = useState<Set<string>>(
    new Set()
  );
  // Actions are matched by tool name rather than id: the backend assigns
  // synthetic per-agent ids to each tool snapshot, so the same tool (e.g.
  // "database_search") gets a different id on every agent. Name is the
  // only identity that's stable across agents.
  const [selectedActionIds, setSelectedActionIds] = useState<Set<string>>(
    new Set()
  );
  const [actionsSearchQuery, setActionsSearchQuery] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);

  useOnMount(() => {
    // Focus the search input when the page loads
    searchInputRef.current?.focus();
  });

  const agents = useMemo(
    () => allAgentsAndFlows.filter((agent) => !isFlowAgent(agent)),
    [allAgentsAndFlows]
  );

  const uniqueActions = useMemo(() => {
    // Keyed by name, not id: the backend assigns each agent's tool
    // snapshots a synthetic id scoped to that agent, so the same tool
    // (e.g. "database_search") shows up with a different id per agent.
    // Deduping by id previously caused the same tool to appear once per
    // agent that has it instead of once overall.
    const actionsMap = new Map<
      string,
      { name: string; display_name: string }
    >();
    agents.forEach((agent) => {
      agent.tools.forEach((tool) => {
        if (
          tool.in_code_tool_id === OPEN_URL_TOOL_ID ||
          tool.name === OPEN_URL_TOOL_ID ||
          tool.name === OPEN_URL_TOOL_NAME
        ) {
          return;
        }
        if (!actionsMap.has(tool.name)) {
          actionsMap.set(tool.name, {
            name: tool.name,
            display_name: tool.display_name,
          });
        }
      });
    });

    const systemToolIds = [
      SEARCH_TOOL_ID,
      IMAGE_GENERATION_TOOL_ID,
      WEB_SEARCH_TOOL_ID,
    ];

    const allActions = Array.from(actionsMap.values());
    const systemTools = allActions.filter((action) =>
      systemToolIds.includes(action.name)
    );
    const otherTools = allActions.filter(
      (action) => !systemToolIds.includes(action.name)
    );

    // Sort each group by display name
    systemTools.sort((a, b) => a.display_name.localeCompare(b.display_name));
    otherTools.sort((a, b) => a.display_name.localeCompare(b.display_name));

    // System tools first, then everything else alphabetically
    return [...systemTools, ...otherTools];
  }, [agents]);

  const filteredActions = useMemo(() => {
    if (!actionsSearchQuery) return uniqueActions;

    const query = actionsSearchQuery.toLowerCase();
    return uniqueActions.filter((action) =>
      action.display_name.toLowerCase().includes(query)
    );
  }, [uniqueActions, actionsSearchQuery]);

  const memoizedCurrentlyVisibleAgents = useMemo(() => {
    return agents.filter((agent) => {
      const nameMatches = agent.name
        .toLowerCase()
        .includes(searchQuery.toLowerCase());
      const labelMatches = agent.labels?.some((label) =>
        label.name.toLowerCase().includes(searchQuery.toLowerCase())
      );

      const isNotUnifiedAgent = agent.id !== 0;

      const agentCreatorId = creatorFilterId(agent.owner);
      const creatorFilter =
        selectedCreatorIds.size === 0 ||
        (!!agentCreatorId && selectedCreatorIds.has(agentCreatorId));

      const actionsFilter =
        selectedActionIds.size === 0 ||
        agent.tools.some((tool) => selectedActionIds.has(tool.name));

      return (
        (nameMatches || labelMatches) &&
        isNotUnifiedAgent &&
        creatorFilter &&
        actionsFilter
      );
    });
  }, [agents, searchQuery, selectedCreatorIds, selectedActionIds]);

  const featuredAgents = [
    ...memoizedCurrentlyVisibleAgents.filter((agent) => agent.featured),
  ];
  const allAgents = memoizedCurrentlyVisibleAgents.filter(
    (agent) => !agent.featured
  );

  const agentCount = featuredAgents.length + allAgents.length;

  const actionsFilterButtonText = useMemo(() => {
    if (selectedActionIds.size === 0) {
      return t("agentsPage.actionsFilterAll");
    } else if (selectedActionIds.size === 1) {
      const selectedName = Array.from(selectedActionIds)[0];
      const action = uniqueActions.find((a) => a.name === selectedName);
      return action ? action.display_name : t("agentsPage.actionsFilterAll");
    } else {
      return t("agentsPage.actionsFilterSelected", {
        count: selectedActionIds.size,
      });
    }
  }, [selectedActionIds, uniqueActions, t]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
        <div className="flex-1 min-w-0">
          <InputTypeIn
            ref={searchInputRef}
            placeholder={t("agentsPage.searchAgentsPlaceholder")}
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            leftSearchIcon
          />
        </div>
        <div className="flex flex-row items-center gap-2 shrink-0">
          <CreatorFilterPopover
            agents={agents}
            selectedCreatorIds={selectedCreatorIds}
            setSelectedCreatorIds={setSelectedCreatorIds}
          />
          <Popover open={actionsFilterOpen} onOpenChange={setActionsFilterOpen}>
            <Popover.Trigger asChild>
              <FilterButton
                leftIcon={SvgActions}
                transient={actionsFilterOpen}
                active={selectedActionIds.size > 0}
                onClear={() => setSelectedActionIds(new Set())}
              >
                {actionsFilterButtonText}
              </FilterButton>
            </Popover.Trigger>
            <Popover.Content align="end">
              <PopoverMenu>
                {[
                  <InputTypeIn
                    key="actions"
                    placeholder={t("agentsPage.filterActionsPlaceholder")}
                    variant="internal"
                    leftSearchIcon
                    value={actionsSearchQuery}
                    onChange={(e) => setActionsSearchQuery(e.target.value)}
                  />,
                  ...filteredActions.flatMap((action, index) => {
                    const isSelected = selectedActionIds.has(action.name);
                    const systemIcon = SYSTEM_TOOL_ICONS[action.name];
                    const isSystemTool = !!systemIcon;

                    const nextAction = filteredActions[index + 1];
                    const nextIsSystemTool = nextAction
                      ? !!SYSTEM_TOOL_ICONS[nextAction.name]
                      : false;
                    const needsSeparator =
                      isSystemTool && nextAction && !nextIsSystemTool;

                    const icon = systemIcon ? systemIcon : SvgActions;

                    const lineItem = (
                      <LineItem
                        key={action.name}
                        icon={icon}
                        selected={isSelected}
                        emphasized
                        onClick={() => {
                          setSelectedActionIds((prev) => {
                            const newSet = new Set(prev);
                            if (newSet.has(action.name)) {
                              newSet.delete(action.name);
                            } else {
                              newSet.add(action.name);
                            }
                            return newSet;
                          });
                        }}
                      >
                        {action.display_name}
                      </LineItem>
                    );

                    return needsSeparator ? [lineItem, null] : [lineItem];
                  }),
                ]}
              </PopoverMenu>
            </Popover.Content>
          </Popover>
        </div>
      </div>

      {isLoading ? (
        <AgentsGridSkeleton count={4} />
      ) : agentCount === 0 ? (
        <Text
          as="p"
          className="w-full h-full flex flex-col items-center justify-center py-12"
          text03
        >
          {t("agentsPage.noAgentsFound")}
        </Text>
      ) : (
        <>
          <AgentsSection
            title={t("agentsPage.featuredAgentsTitle")}
            description={t("agentsPage.featuredAgentsDescription")}
            agents={featuredAgents}
          />
          {featuredAgents.length > 0 && allAgents.length > 0 && (
            <TextSeparator text={t("agentsPage.allAgentsSectionTitle")} />
          )}
          <AgentsSection
            title={
              featuredAgents.length > 0
                ? ""
                : t("agentsPage.allAgentsSectionTitle")
            }
            agents={allAgents}
          />
        </>
      )}
    </div>
  );
}
