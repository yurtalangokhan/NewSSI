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
  iterations?: NodeIterationData[];
}
