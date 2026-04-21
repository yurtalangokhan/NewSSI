"use client";

import { use, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAgent } from "@/hooks/useAgents";
import AgentEditorPage from "@/refresh-pages/AgentEditorPage";
import * as AppLayouts from "@/layouts/app-layouts";

export interface PageProps {
  params: Promise<{ id: string }>;
}

export default function Page(props: PageProps) {
  const router = useRouter();
  const { id } = use(props.params);
  const agentId = parseInt(id);
  const hasLoadedOnce = useRef(false);

  // Call hook unconditionally (passes null when ID is invalid)
  const { agent, isLoading, refresh } = useAgent(
    isNaN(agentId) ? null : agentId
  );

  // Handle invalid ID (NaN)
  useEffect(() => {
    if (isNaN(agentId)) {
      router.push("/app");
    }
  }, [agentId, router]);

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

  // Show nothing while redirecting or loading
  if (isLoading || !agent) return null;

  return (
    <AppLayouts.Root>
      <AgentEditorPage agent={agent} refreshAgent={refresh} />
    </AppLayouts.Root>
  );
}
