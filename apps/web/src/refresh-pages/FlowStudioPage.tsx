"use client";

import { useRouter } from "next/navigation";
import type { Route } from "next";
import FlowAgentEditorPage from "@/refresh-pages/FlowAgentEditorPage";

export interface FlowStudioPageProps {
  definitionId: string;
}

/**
 * The flow studio shell.
 *
 * Deliberately does NOT render inside AppLayouts.Root: the canvas is the
 * page here, and the app sidebar would take width the graph needs. The
 * way back to the rest of the app is the top bar's exit button, not the
 * global navigation.
 */
export default function FlowStudioPage({ definitionId }: FlowStudioPageProps) {
  const router = useRouter();

  return (
    <div
      data-testid="flow-studio-root"
      className="flex h-screen w-screen flex-col overflow-hidden bg-background-tint-00"
    >
      <FlowAgentEditorPage
        agentDefinitionId={definitionId}
        onExited={() => router.push("/app/agents?tab=flows" as Route)}
      />
    </div>
  );
}
