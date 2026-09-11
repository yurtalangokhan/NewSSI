"use client";

import { useTranslation } from "react-i18next";
import { useRouter, useSearchParams } from "next/navigation";
import Text from "@/components/ui/text";
import Title from "@/components/ui/title";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import CreateButton from "@/refresh-components/buttons/CreateButton";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { AgentsGridSkeleton } from "@/refresh-components/skeletons/AgentCardSkeleton";
import { ErrorCallout } from "@/components/ErrorCallout";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useState, useMemo } from "react";
import AgentCard from "@/sections/cards/AgentCard";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { useAgents } from "@/hooks/useAgents";
import Tabs from "@/refresh-components/Tabs";
import AgentAccessGroupsTab, {
  AgentAccessGroupsSkeleton,
} from "./AgentAccessGroupsTab";

const ResolvedAccessGroupsSkeleton = AgentAccessGroupsSkeleton ?? (() => null);
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import FlowsTabContent from "@/refresh-pages/agents/FlowsTabContent";
import FlowSettingsModal from "@/sections/modals/FlowSettingsModal";
import { useCreateModal } from "@/refresh-components/contexts/ModalContext";
import { isFlowAgent } from "@/lib/flows/flowAgent";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";

function AgentCatalog({
  agents,
  searchQuery,
  onSearchQueryChange,
  isLoading,
}: {
  agents: MinimalPersonaSnapshot[];
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  isLoading?: boolean;
}) {
  const { t } = useTranslation();

  const filteredAgents = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    if (!normalizedQuery) {
      return agents;
    }

    return agents.filter((agent) => {
      const name = agent.name?.toLowerCase() || "";
      const description = agent.description?.toLowerCase() || "";
      const owner = agent.owner?.email?.toLowerCase() || "";
      return (
        name.includes(normalizedQuery) ||
        description.includes(normalizedQuery) ||
        owner.includes(normalizedQuery)
      );
    });
  }, [agents, searchQuery]);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Title>{t("admin.agents.catalogTitle")}</Title>
      </div>

      <Text>{t("admin.agents.catalogDescription")}</Text>

      <InputTypeIn
        placeholder={t("admin.agents.searchPlaceholder")}
        value={searchQuery}
        onChange={(event) => onSearchQueryChange(event.target.value)}
        leftSearchIcon
      />

      {isLoading ? (
        <AgentsGridSkeleton count={4} />
      ) : filteredAgents.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {filteredAgents
            .slice()
            .sort((a, b) => {
              if (typeof a.id === "number" && typeof b.id === "number") {
                return b.id - a.id;
              }
              return a.name.localeCompare(b.name);
            })
            .map((agent) => (
              <AgentCard
                key={`${agent.builtin_persona ? "builtin" : "agent"}-${
                  agent.external_id ?? agent.id
                }`}
                agent={agent}
              />
            ))}
        </div>
      ) : (
        <div className="mt-2 p-6 border border-border rounded-lg bg-background-weak text-center">
          <Text>{t("admin.agents.noSearchResults")}</Text>
        </div>
      )}
    </div>
  );
}

/** Mirrors AgentCatalog's heading so the Flows tab is not the one surface
 *  that drops straight into a search box. The list itself is the shared
 *  FlowsTabContent, which /app/agents uses under its own page header — so
 *  the heading lives here rather than inside that component. */
function FlowCatalog({
  agents,
  isLoading,
}: {
  agents: MinimalPersonaSnapshot[];
  isLoading: boolean;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Title>{t("admin.agents.flowCatalogTitle")}</Title>
      </div>

      <Text>{t("admin.agents.flowCatalogDescription")}</Text>

      <FlowsTabContent agents={agents} isLoading={isLoading} />
    </div>
  );
}

const ADMIN_AGENTS_TABS = ["catalog", "flows", "access-groups"] as const;
type AdminAgentsTab = (typeof ADMIN_AGENTS_TABS)[number];

function tabFromParam(value: string | null): AdminAgentsTab {
  return ADMIN_AGENTS_TABS.includes(value as AdminAgentsTab)
    ? (value as AdminAgentsTab)
    : "catalog";
}

export default function Page() {
  const { t } = useTranslation();
  const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.AGENTS]!;
  const router = useRouter();
  const searchParams = useSearchParams();
  const [searchQuery, setSearchQuery] = useState("");
  const {
    agents: catalogAgents,
    isLoading: isCatalogLoading,
    error: catalogError,
  } = useAgents();
  const createFlowModal = useCreateModal();

  // The tab lives in the URL so an admin can link straight to it and a
  // reload does not drop them back on the catalog. Seeded from ?tab= and
  // written back on change, the same contract as /app/agents.
  const urlTab = tabFromParam(searchParams.get("tab"));
  const [activeTab, setActiveTab] = useState<AdminAgentsTab>(urlTab);
  const [prevUrlTab, setPrevUrlTab] = useState<AdminAgentsTab>(urlTab);
  if (prevUrlTab !== urlTab) {
    setPrevUrlTab(urlTab);
    setActiveTab(urlTab);
  }

  // Which way the incoming panel slides in from — same treatment as
  // /app/agents, so moving right in the tab strip moves the content left.
  const [direction, setDirection] = useState(0);
  const shouldReduceMotion = useReducedMotion();

  function selectTab(next: AdminAgentsTab) {
    if (next === activeTab) return;
    setDirection(
      ADMIN_AGENTS_TABS.indexOf(next) > ADMIN_AGENTS_TABS.indexOf(activeTab)
        ? 1
        : -1
    );
    setActiveTab(next);
    router.replace(
      next === "catalog" ? "/admin/agents" : `/admin/agents?tab=${next}`
    );
  }

  const tabContentVariants = {
    enter: (dir: number) => ({
      x: shouldReduceMotion ? 0 : dir > 0 ? 20 : -20,
      opacity: 0,
      filter: shouldReduceMotion ? "none" : "blur(2px)",
    }),
    center: { x: 0, opacity: 1, filter: "blur(0px)" },
    exit: (dir: number) => ({
      x: shouldReduceMotion ? 0 : dir > 0 ? -20 : 20,
      opacity: 0,
      filter: shouldReduceMotion ? "none" : "blur(2px)",
    }),
  };

  const tabContentTransition = {
    duration: 0.22,
    ease: [0.16, 1, 0.3, 1] as const,
  };

  // Snappier than the panel: the button is small and sits still, so it
  // should settle before the panel finishes sliding.
  const ctaTransition = { duration: 0.16, ease: "easeOut" as const };

  // Flows are personas too, but they are a different kind of thing with a
  // different card, editor and lifecycle — counting them as agents made
  // every headline number here wrong. Split once, read everywhere.
  const agentsOnly = useMemo(
    () => catalogAgents.filter((agent) => !isFlowAgent(agent)),
    [catalogAgents]
  );
  const flowsOnly = useMemo(
    () => catalogAgents.filter(isFlowAgent),
    [catalogAgents]
  );

  // Four tiles, one row: the metrics grid is xl:grid-cols-4, and a fifth
  // tile wraps into a ragged second row. "Visible agents" was the easy cut
  // — persona_controller serializes is_visible as a hardcoded True on every
  // branch, so it could never differ from the total. "Public agents" went
  // with it: a persona's sharing state is already on its own card, and the
  // tile carried no signal next to the total either.
  const toolEnabledAgentsCount = agentsOnly.filter(
    (agent) =>
      (agent.tools?.length ?? 0) > 0 || (agent.mcp_tools?.length ?? 0) > 0
  ).length;
  const publishedFlowsCount = flowsOnly.filter(
    (flow) =>
      flow.flow_published_version_no !== null &&
      flow.flow_published_version_no !== undefined
  ).length;

  return (
    <SettingsLayouts.Root>
      <createFlowModal.Provider>
        <FlowSettingsModal mode="create" />
      </createFlowModal.Provider>

      <SettingsLayouts.Header
        icon={route.icon}
        title={t(route.titleKey || "", { defaultValue: route.title })}
        description={
          route.descriptionKey
            ? t(route.descriptionKey, { defaultValue: route.description })
            : route.description
        }
        rightChildren={
          // The CTA swaps with the tab, so it cross-fades rather than
          // snapping — same treatment and timing as /app/agents. Keyed per
          // button so AnimatePresence sees a genuine swap, not a re-render.
          <AnimatePresence mode="wait" initial={false}>
            {activeTab === "flows" ? (
              <motion.div
                key="admin-new-flow-button"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={ctaTransition}
              >
                {/* A flow is created through the metadata modal, not the
                    classic agent form. */}
                <CreateButton
                  data-testid="admin-agents-new-flow-button"
                  onClick={() => createFlowModal.toggle(true)}
                >
                  {t("admin.agents.createFlowButton", {
                    defaultValue: "Create Flow",
                  })}
                </CreateButton>
              </motion.div>
            ) : (
              <motion.div
                key="admin-new-agent-button"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={ctaTransition}
              >
                <CreateButton
                  data-testid="admin-agents-new-agent-button"
                  href="/app/agents/create"
                >
                  {t("admin.agents.createButton")}
                </CreateButton>
              </motion.div>
            )}
          </AnimatePresence>
        }
        separator
      />

      <SettingsLayouts.Body>
        {isCatalogLoading && (
          <div className="flex flex-col gap-4">
            <AdminOverviewPanel
              icon={route.icon}
              title={t("admin.agents.workspaceTitle", {
                defaultValue: "Agent workspace",
              })}
              description={t("admin.agents.workspaceDescription", {
                defaultValue:
                  "Manage the assistant catalog, access groups, and the tools that shape chat behavior.",
              })}
              isLoading={true}
            />

            <Tabs value={activeTab}>
              <Tabs.List variant="contained">
                <Tabs.Trigger value="catalog">
                  {t("admin.agents.agentsTab", { defaultValue: "Agents" })}
                </Tabs.Trigger>
                <Tabs.Trigger value="flows">
                  {t("admin.agents.flowsTab", { defaultValue: "Flows" })}
                </Tabs.Trigger>
                <Tabs.Trigger value="access-groups">
                  {t("admin.agents.accessGroupsTab", {
                    defaultValue: "Access groups",
                  })}
                </Tabs.Trigger>
              </Tabs.List>
            </Tabs>

            {activeTab === "access-groups" ? (
              <ResolvedAccessGroupsSkeleton />
            ) : (
              <div className="flex flex-col gap-4">
                <div>
                  <Title>
                    {activeTab === "flows"
                      ? t("admin.agents.flowCatalogTitle")
                      : t("admin.agents.catalogTitle")}
                  </Title>
                </div>
                <Text>
                  {activeTab === "flows"
                    ? t("admin.agents.flowCatalogDescription")
                    : t("admin.agents.catalogDescription")}
                </Text>

                <div className="h-10 w-full rounded-08 border border-border-01 bg-background-neutral-00 flex items-center px-3 gap-2">
                  <div className="h-4 w-4 rounded-full bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                  <div className="h-4 w-44 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                </div>

                <AgentsGridSkeleton count={4} />
              </div>
            )}
          </div>
        )}

        {catalogError && (
          <ErrorCallout
            errorTitle={t("admin.agents.errorTitle")}
            errorMsg={
              catalogError?.info?.message ||
              catalogError?.info?.detail ||
              t("admin.agents.errorUnknown")
            }
          />
        )}

        {!isCatalogLoading && !catalogError && (
          <>
            <AdminOverviewPanel
              icon={route.icon}
              title={t("admin.agents.workspaceTitle", {
                defaultValue: "Agent workspace",
              })}
              description={t("admin.agents.workspaceDescription", {
                defaultValue:
                  "Manage the assistant catalog, access groups, and the tools that shape chat behavior.",
              })}
              metrics={[
                {
                  label: t("admin.agents.totalAgentsLabel", {
                    defaultValue: "Total agents",
                  }),
                  value: String(agentsOnly.length),
                  tone: agentsOnly.length > 0 ? "success" : "warning",
                },
                {
                  label: t("admin.agents.toolEnabledAgentsLabel", {
                    defaultValue: "Tool-enabled",
                  }),
                  value: String(toolEnabledAgentsCount),
                  tone: toolEnabledAgentsCount > 0 ? "success" : "neutral",
                },
                {
                  label: t("admin.agents.totalFlowsLabel", {
                    defaultValue: "Total flows",
                  }),
                  value: String(flowsOnly.length),
                },
                {
                  // A flow with nothing published cannot be chatted with at
                  // all, so "some flows, none published" is worth flagging.
                  label: t("admin.agents.publishedFlowsLabel", {
                    defaultValue: "Published flows",
                  }),
                  value: String(publishedFlowsCount),
                  tone:
                    flowsOnly.length > 0 && publishedFlowsCount === 0
                      ? "warning"
                      : "neutral",
                },
              ]}
            />
            <Tabs
              value={activeTab}
              onValueChange={(value) => selectTab(value as AdminAgentsTab)}
            >
              <Tabs.List variant="contained">
                <Tabs.Trigger
                  value="catalog"
                  data-testid="admin-agents-tab-catalog"
                >
                  {t("admin.agents.agentsTab", { defaultValue: "Agents" })}
                </Tabs.Trigger>
                <Tabs.Trigger
                  value="flows"
                  data-testid="admin-agents-tab-flows"
                >
                  {t("admin.agents.flowsTab", { defaultValue: "Flows" })}
                </Tabs.Trigger>
                <Tabs.Trigger
                  value="access-groups"
                  data-testid="admin-agents-tab-access-groups"
                >
                  {t("admin.agents.accessGroupsTab", {
                    defaultValue: "Access groups",
                  })}
                </Tabs.Trigger>
              </Tabs.List>
            </Tabs>

            {/* Rendered outside Tabs.Content on purpose: Radix unmounts the
                inactive panel, so an exit animation never gets to play from
                in there. /app/agents animates its tabs the same way — the
                strip switches, the panel below cross-fades and slides.

                This also sidesteps Tabs.Content's Section, whose alignItems
                defaults to "center" and shrink-wrapped the panel to its own
                intrinsic width instead of filling the row. */}
            <div className="w-full overflow-hidden">
              <AnimatePresence mode="wait" initial={false} custom={direction}>
                <motion.div
                  key={activeTab}
                  custom={direction}
                  variants={tabContentVariants}
                  initial="enter"
                  animate="center"
                  exit="exit"
                  transition={tabContentTransition}
                  className="w-full"
                  data-testid={`admin-agents-panel-${activeTab}`}
                >
                  {activeTab === "catalog" && (
                    <AgentCatalog
                      agents={agentsOnly}
                      searchQuery={searchQuery}
                      onSearchQueryChange={setSearchQuery}
                      isLoading={isCatalogLoading}
                    />
                  )}
                  {activeTab === "flows" && (
                    <FlowCatalog
                      agents={catalogAgents}
                      isLoading={isCatalogLoading}
                    />
                  )}
                  {activeTab === "access-groups" && (
                    <AgentAccessGroupsTab agents={catalogAgents} />
                  )}
                </motion.div>
              </AnimatePresence>
            </div>
          </>
        )}
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
