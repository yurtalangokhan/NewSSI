import type { KnowledgeEvidence } from "@/lib/api/domains/chat/knowledge-evidence-types";

export interface ToolInvocationDetail {
  index: number;
  callId?: string | null;
  status: "running" | "done" | "error";
  durationMs: number | null;
  input?: unknown;
  output?: unknown;
}

export interface NodeToolExecution {
  toolName: string;
  label: string;
  callCount: number;
  durationMs: number | null;
  status: "running" | "done" | "error";
  invocations: ToolInvocationDetail[];
}

export interface NodeIterationData {
  iteration: number;
  thinking?: string;
  thinkingDurationMs?: number | null;
  tools?: NodeToolExecution[];
  output?: string;
  /** What this iteration's knowledge searches retrieved. */
  evidence?: KnowledgeEvidence[];
  status: "running" | "done" | "error";
  durationMs: number | null;
}

export interface NodeExecutionData {
  nodeId: string;
  stageKey?: string;
  label?: string;
  status: "queued" | "running" | "done" | "error";
  durationMs: number | null;
  thinking?: string;
  thinkingDurationMs?: number | null;
  tools: NodeToolExecution[];
  output?: string;
  /** What the node's knowledge searches retrieved, across iterations. */
  evidence?: KnowledgeEvidence[];
  iterations?: NodeIterationData[];
}
