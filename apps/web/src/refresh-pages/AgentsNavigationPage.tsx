"use client";

import { useMemo, useState, useRef } from "react";
import AgentCard from "@/sections/cards/AgentCard";
import { useUser } from "@/providers/UserProvider";
import { getAgentPageAccess } from "@/lib/agentPageAccess";
import {
  checkUserOwnsAgent as checkUserOwnsAgent,
  UNKNOWN_AGENT_OWNER_EMAIL,
} from "@/lib/agents";
import { useAgents } from "@/hooks/useAgents";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import Text from "@/refresh-components/texts/Text";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import TextSeparator from "@/refresh-components/TextSeparator";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import Tabs from "@/refresh-components/Tabs";
import FilterButton from "@/refresh-components/buttons/FilterButton";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import LineItem from "@/refresh-components/buttons/LineItem";
import { Button } from "@opal/components";
import {
  SEARCH_TOOL_ID,
  IMAGE_GENERATION_TOOL_ID,
  OPEN_URL_TOOL_ID,
  OPEN_URL_TOOL_NAME,
  WEB_SEARCH_TOOL_ID,
  SYSTEM_TOOL_ICONS,
} from "@/app/app/components/tools/constants";
import {
  SvgActions,
  SvgCheck,
  SvgOnyxOctagon,
  SvgPlus,
  SvgUser,
} from "@opal/icons";
import useOnMount from "@/hooks/useOnMount";
import { useTranslation } from "react-i18next";

// Synthetic id used to collapse every agent whose owner account no longer
// resolves (backend returns UNKNOWN_AGENT_OWNER_EMAIL) into a single
// "Deleted user" entry in the creator filter, instead of one entry per
// distinct orphaned owner id.
const UNKNOWN_OWNER_FILTER_ID = "__unknown_owner__";

function creatorFilterId(owner: { id: string; email: string } | null | undefined) {
  if (!owner) return undefined;
  return owner.email === UNKNOWN_AGENT_OWNER_EMAIL
    ? UNKNOWN_OWNER_FILTER_ID
    : owner.id;
}

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
            return a.name.localeCompare(b.name);
          })
          .map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
      </div>
    </div>
  );
}

export default function AgentsNavigationPage() {
  const { agents, isLoading: isLoadingAgents } = useAgents();
  const [creatorFilterOpen, setCreatorFilterOpen] = useState(false);
  const [actionsFilterOpen, setActionsFilterOpen] = useState(false);
  const { user, hasPermission } = useUser();
  const { canCreateAgent, canViewPersonalTab } = getAgentPageAccess({
    canCreateAgent: hasPermission("agent:create"),
    canListAgents: hasPermission("agent:list"),
  });
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"all" | "your">("all");
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
  const [creatorSearchQuery, setCreatorSearchQuery] = useState("");
  const [actionsSearchQuery, setActionsSearchQuery] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);

  useOnMount(() => {
    // Focus the search input when the page loads
    searchInputRef.current?.focus();
  });

  const uniqueCreators = useMemo(() => {
    const creatorsMap = new Map<string, { id: string; email: string }>();
    agents.forEach((agent) => {
      if (!agent.owner) return;
      const id = creatorFilterId(agent.owner);
      if (!id) return;
      if (id === UNKNOWN_OWNER_FILTER_ID) {
        creatorsMap.set(id, { id, email: t("agentsPage.unknownOwner") });
      } else {
        creatorsMap.set(id, agent.owner);
      }
    });

    let creators = Array.from(creatorsMap.values()).sort((a, b) =>
      a.email.localeCompare(b.email)
    );

    // Add current user if not in the list, and put them first
    if (user) {
      const hasCurrentUser = creators.some((c) => c.id === user.id);

      if (!hasCurrentUser) {
        creators = [{ id: user.id, email: user.email }, ...creators];
      } else {
        // Sort to put current user first
        creators = creators.sort((a, b) => {
          if (a.id === user.id) return -1;
          if (b.id === user.id) return 1;
          return 0;
        });
      }
    }

    return creators;
  }, [agents, user, t]);

  const filteredCreators = useMemo(() => {
    if (!creatorSearchQuery) return uniqueCreators;

    return uniqueCreators.filter((creator) =>
      creator.email.toLowerCase().includes(creatorSearchQuery.toLowerCase())
    );
  }, [uniqueCreators, creatorSearchQuery]);

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

      const mineFilter =
        activeTab === "your" ? checkUserOwnsAgent(user, agent) : true;
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
        mineFilter &&
        isNotUnifiedAgent &&
        creatorFilter &&
        actionsFilter
      );
    });
  }, [
    agents,
    searchQuery,
    activeTab,
    user,
    selectedCreatorIds,
    selectedActionIds,
  ]);

  const featuredAgents = [
    ...memoizedCurrentlyVisibleAgents.filter((agent) => agent.featured),
  ];
  const allAgents = memoizedCurrentlyVisibleAgents.filter(
    (agent) => !agent.featured
  );

  const agentCount = featuredAgents.length + allAgents.length;

  const creatorFilterButtonText = useMemo(() => {
    if (selectedCreatorIds.size === 0) {
      return t("agentsPage.creatorFilterEveryone");
    } else if (selectedCreatorIds.size === 1) {
      const selectedId = Array.from(selectedCreatorIds)[0];
      const creator = uniqueCreators.find((c) => c.id === selectedId);
      return creator
        ? t("agentsPage.creatorFilterBy", { email: creator.email })
        : t("agentsPage.creatorFilterEveryone");
    } else {
      return t("agentsPage.creatorFilterCount", {
        count: selectedCreatorIds.size,
      });
    }
  }, [selectedCreatorIds, uniqueCreators, t]);

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
    <SettingsLayouts.Root
      data-testid="AgentsPage/container"
      aria-label="Agents Page"
    >
      <SettingsLayouts.Header
        icon={SvgOnyxOctagon}
        title={t("agentsPage.title")}
        description={t("agentsPage.description")}
        rightChildren={
          canCreateAgent ? (
            <Button
              href="/app/agents/create"
              icon={SvgPlus}
              aria-label="AgentsPage/new-agent-button"
            >
              {t("agentsPage.newAgentButton")}
            </Button>
          ) : undefined
        }
      >
        <div className="flex flex-col gap-2">
          <div className="flex flex-row items-center gap-2">
            <div className="flex-[2]">
              <InputTypeIn
                ref={searchInputRef}
                placeholder={t("agentsPage.searchAgentsPlaceholder")}
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                leftSearchIcon
              />
            </div>
            {canViewPersonalTab && (
              <div className="flex-1">
                <Tabs
                  value={activeTab}
                  onValueChange={(value) =>
                    setActiveTab(value as "all" | "your")
                  }
                >
                  <Tabs.List>
                    <Tabs.Trigger value="all">
                      {t("agentsPage.allAgentsTab")}
                    </Tabs.Trigger>
                    <Tabs.Trigger value="your">
                      {t("agentsPage.yourAgentsTab")}
                    </Tabs.Trigger>
                  </Tabs.List>
                </Tabs>
              </div>
            )}
          </div>
          <div className="flex flex-row gap-2">
            <Popover
              open={creatorFilterOpen}
              onOpenChange={setCreatorFilterOpen}
            >
              <Popover.Trigger asChild>
                <FilterButton
                  leftIcon={SvgUser}
                  active={selectedCreatorIds.size > 0}
                  transient={creatorFilterOpen}
                  onClear={() => setSelectedCreatorIds(new Set())}
                >
                  {creatorFilterButtonText}
                </FilterButton>
              </Popover.Trigger>
              <Popover.Content align="start">
                <PopoverMenu>
                  {[
                    <InputTypeIn
                      key="created-by"
                      placeholder={t("agentsPage.createdByPlaceholder")}
                      variant="internal"
                      leftSearchIcon
                      value={creatorSearchQuery}
                      onChange={(e) => setCreatorSearchQuery(e.target.value)}
                    />,
                    ...filteredCreators.flatMap((creator, index) => {
                      const isSelected = selectedCreatorIds.has(creator.id);
                      const isCurrentUser = user && creator.id === user.id;

                      // Check if we need to add a separator after this item
                      const nextCreator = filteredCreators[index + 1];
                      const nextIsCurrentUser =
                        user && nextCreator && nextCreator.id === user.id;
                      const needsSeparator =
                        isCurrentUser && nextCreator && !nextIsCurrentUser;

                      // Determine icon: Check if selected, User icon if current user, otherwise no icon
                      const icon = isCurrentUser
                        ? SvgUser
                        : isSelected
                          ? SvgCheck
                          : () => null;

                      const lineItem = (
                        <LineItem
                          key={creator.id}
                          icon={icon}
                          selected={isSelected}
                          emphasized
                          onClick={() => {
                            setSelectedCreatorIds((prev) => {
                              const newSet = new Set(prev);
                              if (newSet.has(creator.id)) {
                                newSet.delete(creator.id);
                              } else {
                                newSet.add(creator.id);
                              }
                              return newSet;
                            });
                          }}
                        >
                          {creator.email}
                        </LineItem>
                      );

                      // Return the line item, and optionally a separator
                      return needsSeparator ? [lineItem, null] : [lineItem];
                    }),
                  ]}
                </PopoverMenu>
              </Popover.Content>
            </Popover>
            <Popover
              open={actionsFilterOpen}
              onOpenChange={setActionsFilterOpen}
            >
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
              <Popover.Content align="start">
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

                      // Check if we need to add a separator after this item
                      const nextAction = filteredActions[index + 1];
                      const nextIsSystemTool = nextAction
                        ? !!SYSTEM_TOOL_ICONS[nextAction.name]
                        : false;
                      const needsSeparator =
                        isSystemTool && nextAction && !nextIsSystemTool;

                      // Determine icon: system icon if available, otherwise Actions icon
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
      </SettingsLayouts.Header>

      {/* Agents List */}
      <SettingsLayouts.Body>
        {isLoadingAgents ? (
          <div className="w-full h-full flex items-center justify-center py-12">
            <SimpleLoader className="h-6 w-6" />
          </div>
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
            <AgentsSection
              title={t("agentsPage.allAgentsSectionTitle")}
              agents={allAgents}
            />
            <TextSeparator
              count={agentCount}
              text={
                agentCount === 1
                  ? t("agentsPage.agentSingular")
                  : t("agentsPage.agentPlural")
              }
            />
          </>
        )}
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
