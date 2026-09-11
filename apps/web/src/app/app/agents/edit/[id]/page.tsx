"use client";

import { use, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useAgent } from "@/hooks/useAgents";
import AgentEditorPage from "@/refresh-pages/AgentEditorPage";
import * as AppLayouts from "@/layouts/app-layouts";
import AgentEditorSkeleton from "@/refresh-components/skeletons/AgentEditorSkeleton";

export interface PageProps {
  params: Promise<{ id: string }>;
}

export default function Page(props: PageProps) {
  const router = useRouter();
  const { id } = use(props.params);
  const numericId = Number.parseInt(id, 10);
  const agentId = Number.isNaN(numericId) ? id : numericId;
  const hasLoadedOnce = useRef(false);

  // Call hook unconditionally (passes null when ID is invalid)
  const { agent, isLoading, refresh } = useAgent(agentId);

  // Track when loading has completed at least once to avoid false redirects
  useEffect(() => {
    if (!isLoading) {
      hasLoadedOnce.current = true;
    }
  }, [isLoading]);

  // Redirect to home only after loading has completed and agent is not found
  useEffect(() => {
    if (hasLoadedOnce.current && !isLoading && !agent) {
      router.push("/app");
    }
  }, [isLoading, agent, router]);

  // Flows have their own full-screen studio now — this classic editor
  // never renders one, it only redirects (P4→flow-separation).
  useEffect(() => {
    if (agent?.graph_schema === "flow" && agent.agent_definition_id) {
      router.replace(`/app/flows/${agent.agent_definition_id}` as Route);
    }
  }, [agent, router]);

  // Show a skeleton while the agent loads or we're about to redirect
  if (isLoading || !agent) {
    return (
      <AppLayouts.Root>
        <AgentEditorSkeleton isEditing={true} />
      </AppLayouts.Root>
    );
  }
  if (agent.graph_schema === "flow") return null;

  return (
    <AppLayouts.Root>
      <AgentEditorPage agent={agent} refreshAgent={refresh} />
    </AppLayouts.Root>
  );
}
