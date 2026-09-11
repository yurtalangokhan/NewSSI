"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useUser } from "@/providers/UserProvider";
import { getAgentPageAccess } from "@/lib/agentPageAccess";
import { useAgents } from "@/hooks/useAgents";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Tabs from "@/refresh-components/Tabs";
import { Button } from "@opal/components";
import { SvgOnyxOctagon, SvgPlus } from "@opal/icons";
import { useTranslation } from "react-i18next";
import { useCreateModal } from "@/refresh-components/contexts/ModalContext";
import AgentsTabContent from "@/refresh-pages/agents/AgentsTabContent";
import FlowsTabContent from "@/refresh-pages/agents/FlowsTabContent";
import FlowSettingsModal from "@/sections/modals/FlowSettingsModal";
import { motion, AnimatePresence, useReducedMotion } from "motion/react";

type AgentsSurface = "agents" | "flows";

const surfaceOrder: Record<AgentsSurface, number> = {
  agents: 0,
  flows: 1,
};

export default function AgentsNavigationPage() {
  const { agents, isLoading: isLoadingAgents } = useAgents();
  const { hasPermission } = useUser();
  const { canCreateAgent } = getAgentPageAccess({
    canCreateAgent: hasPermission("agent:create"),
    canListAgents: hasPermission("agent:list"),
  });
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const targetSurface: AgentsSurface =
    searchParams.get("tab") === "flows" ? "flows" : "agents";

  const [activeSurface, setActiveSurface] =
    useState<AgentsSurface>(targetSurface);
  const [direction, setDirection] = useState<number>(0);
  const [prevTarget, setPrevTarget] = useState<AgentsSurface>(targetSurface);
  const shouldReduceMotion = useReducedMotion();
  const createFlowModal = useCreateModal();

  if (prevTarget !== targetSurface) {
    setPrevTarget(targetSurface);
    if (targetSurface !== activeSurface) {
      setDirection(
        surfaceOrder[targetSurface] > surfaceOrder[activeSurface] ? 1 : -1
      );
      setActiveSurface(targetSurface);
    }
  }

  function selectSurface(next: AgentsSurface) {
    if (next === activeSurface) return;
    setDirection(surfaceOrder[next] > surfaceOrder[activeSurface] ? 1 : -1);
    setActiveSurface(next);
    router.replace(next === "flows" ? "/app/agents?tab=flows" : "/app/agents");
  }

  const tabContentVariants = {
    enter: (dir: number) => ({
      x: shouldReduceMotion ? 0 : dir > 0 ? 20 : -20,
      opacity: 0,
      filter: shouldReduceMotion ? "none" : "blur(2px)",
    }),
    center: {
      x: 0,
      opacity: 1,
      filter: "blur(0px)",
    },
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

  return (
    <SettingsLayouts.Root
      data-testid="AgentsPage/container"
      aria-label="Agents Page"
    >
      <createFlowModal.Provider>
        <FlowSettingsModal mode="create" />
      </createFlowModal.Provider>

      <SettingsLayouts.Header
        icon={SvgOnyxOctagon}
        title={t("agentsPage.title")}
        description={t("agentsPage.description")}
        rightChildren={
          canCreateAgent ? (
            <AnimatePresence mode="wait" initial={false}>
              {activeSurface === "flows" ? (
                <motion.div
                  key="new-flow-button"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.16, ease: "easeOut" }}
                >
                  <Button
                    icon={SvgPlus}
                    data-testid="AgentsPage/new-flow-button"
                    aria-label="AgentsPage/new-flow-button"
                    onClick={() => createFlowModal.toggle(true)}
                  >
                    {t("flowsPage.newFlowButton")}
                  </Button>
                </motion.div>
              ) : (
                <motion.div
                  key="new-agent-button"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.16, ease: "easeOut" }}
                >
                  <Button
                    href="/app/agents/create"
                    icon={SvgPlus}
                    data-testid="AgentsPage/new-agent-button"
                    aria-label="AgentsPage/new-agent-button"
                  >
                    {t("agentsPage.newAgentButton")}
                  </Button>
                </motion.div>
              )}
            </AnimatePresence>
          ) : undefined
        }
      >
        <Tabs
          value={activeSurface}
          onValueChange={(value) => selectSurface(value as AgentsSurface)}
        >
          <Tabs.List>
            <Tabs.Trigger value="agents" data-testid="agents-page-tab-agents">
              {t("agentsPage.agentsSurfaceTab")}
            </Tabs.Trigger>
            <Tabs.Trigger value="flows" data-testid="agents-page-tab-flows">
              {t("agentsPage.flowsSurfaceTab")}
            </Tabs.Trigger>
          </Tabs.List>
        </Tabs>
      </SettingsLayouts.Header>

      <SettingsLayouts.Body>
        <div className="w-full overflow-hidden">
          <AnimatePresence mode="wait" initial={false} custom={direction}>
            <motion.div
              key={activeSurface}
              custom={direction}
              variants={tabContentVariants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={tabContentTransition}
              className="w-full"
            >
              {activeSurface === "flows" ? (
                <FlowsTabContent agents={agents} isLoading={isLoadingAgents} />
              ) : (
                <AgentsTabContent agents={agents} isLoading={isLoadingAgents} />
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
