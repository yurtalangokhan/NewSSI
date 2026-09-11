/**
 * Pure packet/flow-graph parsing for GraphStageStrip.
 *
 * Everything the strip needs to turn a raw packet list + a flow graph into
 * stage progress, an ordered call sequence and per-node run status — extracted
 * out of the component so the ~950 lines of logic are unit-testable and the
 * component file stays a rendering concern.
 */

import { Packet, PacketType } from "@/app/app/services/streamingModels";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import type { NodeRunStatus } from "@/components/flow-canvas/stores/flowStore";
import type {
  CanvasEdge,
  CanvasNode,
} from "@/components/flow-canvas/types/flow";

export interface StageDefinition {
  key: string;
  /** What's shown in the tag/canvas — prettified for flow nodes. */
  label: string;
  /** What graph_stage_start/end's stage_name actually equals. */
  matchName: string;
  isResource?: boolean;
}

export interface StageTiming {
  startedAt: number | null;
  endedAt: number | null;
  durationMs: number | null;
}

export interface StageProgress {
  runningStageNames: Set<string>;
  completedStageNames: Set<string>;
  stageTimings: Map<string, StageTiming>;
}

export interface ToolInvocation {
  index: number;
  callId?: string | null;
  durationMs: number | null;
  startedAt: number | null;
  endedAt: number | null;
}

export interface NestedToolCall {
  toolName: string;
  label: string;
  callCount: number;
  durationMs: number | null;
  status: "running" | "done";
  invocations: ToolInvocation[];
}

export interface CallEntry {
  key: string;
  matchName: string;
  label: string;
  status: "running" | "done" | "pending";
  callCount: number;
  durationMs: number | null;
  isResource?: boolean;
  tools?: NestedToolCall[];
}

export interface GraphStageStripProps {
  agent: MinimalPersonaSnapshot;
  packets: Packet[];
  packetCount?: number;
}

// Floor for a tool/stage duration: sub-10ms measurements (and the brief window
// before a still-running call reports a real duration) all render as this so a
// completed call never shows "0ms".
export const MIN_STAGE_DURATION_MS = 10;

/**
 * Node types that never become a numbered stage in the timeline: flow
 * boundaries, control flow and plain value producers. They emit no answer
 * text, so a stage for one is an empty group in the chat.
 *
 * The compiler owns this list — `PASSTHROUGH_NODE_TYPES` in
 * `agents/graphs/flow_builder.py`, re-exported from `agents.graphs` — and the
 * server already applies it to live runs, tagging each packet with its
 * `stage_node_id`. This copy is the fallback for legacy packets stored before
 * that attribution existed. `nonStageNodeTypes.test.ts` pins the two lists
 * together, because the inline four-entry version this replaces had silently
 * gone stale as the compiler grew to thirteen.
 */
export const NON_STAGE_NODE_TYPES: ReadonlySet<string> = new Set([
  "ChatInput",
  "ChatOutput",
  "ConditionalRouter",
  "FileInput",
  "HumanInput",
  "Loop",
  "Merge",
  "PromptTemplate",
  "Router",
  "SetVariable",
  "SmartRouter",
  "TextInput",
  "While",
]);

export const CONFIG_NODE_TYPES = new Set([
  "prompttemplate",
  "systemprompt",
  "prompt",
  "llmmodel",
  "ollamamodel",
  "openaimodel",
  "anthropicmodel",
  "memory",
  "longtermmemory",
  "conversationmemory",
  "threadcheckpointer",
  "note",
  "stickynote",
  "datasource",
  "config",
  "settings",
  "auth",
  "mailconfig",
  "mcpconfig",
]);

const CANONICAL_COMPONENT_MAP: Record<string, string> = {
  chatinput: "ChatInput",
  chatoutput: "ChatOutput",
  reactagent: "ReActAgent",
  reactexecutor: "ReActAgent",
  webtools: "WebTools",
  codetools: "CodeTools",
  calculatortools: "CalculatorTools",
  loop: "Loop",
  loopcontrol: "Loop",
  merge: "Merge",
  mergeresults: "Merge",
  llmmodel: "LLMModel",
  memory: "Memory",
  longmemory: "Memory",
  research: "Research",
  analysis: "Analysis",
  synthesis: "Synthesis",
  review: "Review",
};

export function getStringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function extractStageLabel(
  stage: Record<string, unknown>,
  index: number
): string {
  return (
    getStringValue(stage.name) ??
    getStringValue(stage.title) ??
    getStringValue(stage.label) ??
    getStringValue(stage.stage_name) ??
    `Stage ${index + 1}`
  );
}

/** Prettify raw canvas node id (e.g. "node-stage-research" -> "Research", "node-chat-input" -> "ChatInput") */
export function prettifyNodeId(id: string): string {
  if (!id) return "";
  let s = id.replace(/[-_][0-9a-f]{6,}$/i, "");
  s = s.replace(/^node[-_]stage[-_]/i, "");
  s = s.replace(/^stage[-_]/i, "");
  s = s.replace(/^node[-_]/i, "");

  const normalized = s.toLowerCase().replace(/[-_\s]+/g, "");
  if (CANONICAL_COMPONENT_MAP[normalized]) {
    return CANONICAL_COMPONENT_MAP[normalized]!;
  }

  return s
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .trim();
}

/** Check if node is a non-executable config node (like Model or Config) */
export function isConfigNode(typeOrId: string): boolean {
  if (!typeOrId || typeOrId === "templateNode" || typeOrId === "noteNode") {
    return false;
  }
  const clean = typeOrId.toLowerCase().replace(/[-_\s]+/g, "");
  if (CONFIG_NODE_TYPES.has(clean)) return true;
  return (
    typeOrId.startsWith("model_") ||
    typeOrId.startsWith("memory_") ||
    typeOrId.startsWith("config_") ||
    typeOrId.startsWith("node-llm-model") ||
    typeOrId.startsWith("node-long-memory")
  );
}

/** Check if node is a tool resource node offering tools */
export function isToolResourceNode(node: CanvasNode): boolean {
  const tools = node.data?.values?.tools;
  if (Array.isArray(tools) && tools.length > 0) return true;
  const typeOrId = (node.data?.type || node.type || node.id || "")
    .toLowerCase()
    .replace(/[-_\s]+/g, "");
  return (
    typeOrId.includes("tools") ||
    typeOrId.includes("websearch") ||
    typeOrId.includes("codeinterpreter") ||
    typeOrId.includes("calculator")
  );
}

export function getStageDefinitions(
  agent: MinimalPersonaSnapshot
): StageDefinition[] {
  const stageSource =
    Array.isArray(agent.stages) && agent.stages.length > 0
      ? agent.stages
      : Array.isArray(agent.sub_agents) && agent.sub_agents.length > 0
        ? agent.sub_agents
        : [];

  return stageSource
    .map((stage, index) => {
      if (!stage || typeof stage !== "object" || Array.isArray(stage)) {
        return null;
      }

      const stageLabel = extractStageLabel(stage, index);
      const prettified = prettifyNodeId(stageLabel);
      if (
        isConfigNode(stageLabel) ||
        isConfigNode(prettified) ||
        stageLabel.toLowerCase().includes("tool") ||
        prettified.toLowerCase().includes("tool")
      ) {
        return null;
      }
      return {
        key: `${index}-${stageLabel}`,
        label: prettified,
        matchName: stageLabel,
      };
    })
    .filter((stage): stage is StageDefinition => stage !== null);
}

/** Topological order from every ChatInput node to ChatOutput, following
 * execution edges — non-execution config and tool resource nodes are filtered out,
 * and ChatOutput is guaranteed to be at the end. */
export function orderFlowNodes(
  nodes: CanvasNode[],
  edges: CanvasEdge[]
): CanvasNode[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const outgoing = new Map<string, string[]>();

  for (const edge of edges) {
    const sourceNode = byId.get(edge.source);
    if (
      sourceNode &&
      (isConfigNode(sourceNode.data?.type || sourceNode.type || "") ||
        isToolResourceNode(sourceNode))
    ) {
      continue;
    }
    const list = outgoing.get(edge.source) ?? [];
    list.push(edge.target);
    outgoing.set(edge.source, list);
  }

  const visited = new Set<string>();
  const ordered: CanvasNode[] = [];
  const queue = nodes
    .filter(
      (n) =>
        n.data?.type === "ChatInput" ||
        n.id.toLowerCase().startsWith("chatinput") ||
        n.id.toLowerCase().startsWith("chat_input") ||
        n.id === "node-chat-input"
    )
    .map((n) => n.id);

  while (queue.length > 0) {
    const id = queue.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);
    const node = byId.get(id);
    if (
      node &&
      !isConfigNode(node.data?.type || node.type || "") &&
      !isToolResourceNode(node)
    ) {
      ordered.push(node);
    }
    queue.push(...(outgoing.get(id) ?? []));
  }

  for (const node of nodes) {
    if (
      !visited.has(node.id) &&
      !isConfigNode(node.data?.type || node.type || "") &&
      !isToolResourceNode(node)
    ) {
      ordered.push(node);
    }
  }

  // Ensure ChatOutput is placed at the end of the pipeline if present
  const outputIdx = ordered.findIndex(
    (n) =>
      n.data?.type === "ChatOutput" ||
      n.id.toLowerCase().startsWith("chatoutput") ||
      n.id.toLowerCase().startsWith("chat_output") ||
      n.id === "node-chat-output"
  );
  if (outputIdx >= 0 && outputIdx < ordered.length - 1) {
    const [outputNode] = ordered.splice(outputIdx, 1);
    if (outputNode) ordered.push(outputNode);
  }

  return ordered;
}

export function getFlowStageDefinitions(
  nodes: CanvasNode[],
  edges: CanvasEdge[]
): StageDefinition[] {
  return orderFlowNodes(nodes, edges).map((node) => ({
    key: node.id,
    // The component type ("ConditionalRouter", "ChatInput") is the
    // authoritative identity — `translateLabel` maps it through the same
    // `flowCanvas.components.<type>.name` i18n table the rest of the canvas
    // uses. `prettifyNodeId` only covers legacy / typeless nodes.
    label: node.data?.type || prettifyNodeId(node.id),
    matchName: node.id,
    isResource: false,
  }));
}

export function getToolNameToNodeId(nodes: CanvasNode[]): Map<string, string> {
  const map = new Map<string, string>();
  for (const node of nodes) {
    const tools = node.data?.values?.tools;
    if (Array.isArray(tools)) {
      for (const toolName of tools) {
        if (typeof toolName === "string") map.set(toolName, node.id);
      }
    }
    // Fallback: match tool node name / type directly
    const nodeType = (node.data?.type || node.type || "").toLowerCase();
    const nodeId = (node.id || "").toLowerCase();
    if (nodeType.includes("web") || nodeId.includes("web")) {
      map.set("web_search", node.id);
      map.set("fetch_webpage", node.id);
      map.set("search", node.id);
      map.set("open_url", node.id);
    }
    if (
      nodeType.includes("code") ||
      nodeId.includes("code") ||
      nodeType.includes("python") ||
      nodeId.includes("python")
    ) {
      map.set("run_python", node.id);
      map.set("execute_python_code", node.id);
      map.set("execute_bash_command", node.id);
      map.set("python", node.id);
      map.set("code_interpreter", node.id);
      map.set("bash", node.id);
    }
    if (nodeType.includes("mail") || nodeId.includes("mail")) {
      map.set("send_email", node.id);
      map.set("mail", node.id);
    }
    if (nodeType.includes("calc") || nodeId.includes("calc")) {
      map.set("calculate", node.id);
      map.set("calculator", node.id);
    }
  }
  return map;
}

export function getToolNodeIdToAgentNodeId(
  edges: CanvasEdge[],
  nodes: CanvasNode[]
): Map<string, string> {
  const map = new Map<string, string>();
  const byId = new Map(nodes.map((n) => [n.id, n]));

  for (const edge of edges) {
    const sourceNode = byId.get(edge.source);
    const targetNode = byId.get(edge.target);
    if (
      sourceNode &&
      isToolResourceNode(sourceNode) &&
      targetNode &&
      !isToolResourceNode(targetNode)
    ) {
      map.set(edge.source, edge.target);
    } else if (
      targetNode &&
      isToolResourceNode(targetNode) &&
      sourceNode &&
      !isToolResourceNode(sourceNode)
    ) {
      map.set(edge.target, edge.source);
    }
  }
  return map;
}

type StageEvent = {
  type: "start" | "end";
  stageName: string;
  kind: "graph" | "tool";
  timestamp: number;
  callId?: string;
  /** For a tool event: the canvas node id of the stage that was running
   * when the backend emitted it (`stage_node_id`). Exact parent-stage
   * attribution — no graph-position or timing guesswork needed. */
  parentStageNodeId?: string;
};

export function resolveStageEvent(
  packet: Packet,
  toolNameToNodeId: Map<string, string>,
  packetTimestamp: number
): StageEvent | null {
  const obj = packet.obj as unknown as Record<string, unknown>;
  const rawTimestamp =
    typeof obj.timestamp === "number" ? obj.timestamp : packetTimestamp;
  const callId = typeof obj.call_id === "string" ? obj.call_id : undefined;
  const parentStageNodeId =
    typeof obj.stage_node_id === "string" ? obj.stage_node_id : undefined;

  if (
    obj.type === PacketType.GRAPH_STAGE_START ||
    obj.type === PacketType.GRAPH_STAGE_END
  ) {
    const stageName = getStringValue(obj.stage_name);
    if (!stageName) return null;
    return {
      type: obj.type === PacketType.GRAPH_STAGE_START ? "start" : "end",
      stageName,
      kind: "graph",
      timestamp: rawTimestamp,
      callId,
    };
  }

  const toolEvent = (type: "start" | "end", stageName: string): StageEvent => ({
    type,
    stageName,
    kind: "tool",
    timestamp: rawTimestamp,
    callId,
    parentStageNodeId,
  });

  if (obj.type === PacketType.CUSTOM_TOOL_START) {
    const toolName = getStringValue(obj.tool_name);
    const stageName = toolName
      ? toolNameToNodeId.get(toolName) ?? toolName
      : undefined;
    return stageName ? toolEvent("start", stageName) : null;
  }

  if (
    obj.type === PacketType.CUSTOM_TOOL_DELTA &&
    obj.response_type === "tool_result"
  ) {
    const toolName = getStringValue(obj.tool_name);
    const stageName = toolName
      ? toolNameToNodeId.get(toolName) ?? toolName
      : undefined;
    return stageName ? toolEvent("end", stageName) : null;
  }

  if (obj.type === PacketType.PYTHON_TOOL_START) {
    return toolEvent(
      "start",
      toolNameToNodeId.get("execute_python_code") ?? "PythonCode"
    );
  }
  if (obj.type === PacketType.PYTHON_TOOL_DELTA) {
    return toolEvent(
      "end",
      toolNameToNodeId.get("execute_python_code") ?? "PythonCode"
    );
  }

  if (obj.type === PacketType.SEARCH_TOOL_START) {
    return toolEvent("start", toolNameToNodeId.get("web_search") ?? "WebTools");
  }
  if (obj.type === PacketType.SEARCH_TOOL_DOCUMENTS_DELTA) {
    return toolEvent("end", toolNameToNodeId.get("web_search") ?? "WebTools");
  }
  if (obj.type === PacketType.FETCH_TOOL_START) {
    return toolEvent(
      "start",
      toolNameToNodeId.get("fetch_webpage") ?? "WebTools"
    );
  }
  if (obj.type === PacketType.FETCH_TOOL_DOCUMENTS) {
    return toolEvent(
      "end",
      toolNameToNodeId.get("fetch_webpage") ?? "WebTools"
    );
  }

  return null;
}

interface NodeTimingTracker {
  firstStartedAt: number | null;
  endedAt: number | null;
  totalDurationMs: number;
  lastInvocationStart: number | null;
}

export function getStageProgress(
  packets: Packet[],
  stageDefinitions: StageDefinition[],
  toolNameToNodeId: Map<string, string>,
  packetTimestamps: number[]
): StageProgress {
  const knownStageNames = new Set(
    stageDefinitions.map((stage) => stage.matchName)
  );
  const completedStageNames = new Set<string>();
  const runningStageNames = new Set<string>();
  const trackerMap = new Map<string, NodeTimingTracker>();
  let activeGraphStageName: string | null = null;
  const runningToolNames = new Set<string>();

  const getTracker = (name: string): NodeTimingTracker => {
    let tr = trackerMap.get(name);
    if (!tr) {
      tr = {
        firstStartedAt: null,
        endedAt: null,
        totalDurationMs: 0,
        lastInvocationStart: null,
      };
      trackerMap.set(name, tr);
    }
    return tr;
  };

  const closeRunningTools = (ts: number) => {
    for (const toolName of Array.from(runningToolNames)) {
      const tr = getTracker(toolName);
      if (tr.lastInvocationStart !== null) {
        tr.totalDurationMs += Math.max(
          MIN_STAGE_DURATION_MS,
          ts - tr.lastInvocationStart
        );
        tr.lastInvocationStart = null;
      }
      tr.endedAt = ts;
      completedStageNames.add(toolName);
      runningStageNames.delete(toolName);
      runningToolNames.delete(toolName);
    }
  };

  for (let i = 0; i < packets.length; i++) {
    const packet = packets[i];
    if (!packet) continue;
    const ts = packetTimestamps[i] ?? Date.now();
    const event = resolveStageEvent(packet, toolNameToNodeId, ts);
    if (!event) continue;
    const { type, stageName, kind, timestamp } = event;

    if (
      stageDefinitions.length > 0 &&
      !knownStageNames.has(stageName) &&
      kind === "graph"
    ) {
      continue;
    }

    const tr = getTracker(stageName);

    if (kind === "graph") {
      if (type === "start") {
        closeRunningTools(timestamp);
        if (activeGraphStageName && activeGraphStageName !== stageName) {
          const prevTr = getTracker(activeGraphStageName);
          if (prevTr.lastInvocationStart !== null) {
            prevTr.totalDurationMs += Math.max(
              10,
              timestamp - prevTr.lastInvocationStart
            );
            prevTr.lastInvocationStart = null;
          }
          prevTr.endedAt = timestamp;
          completedStageNames.add(activeGraphStageName);
          runningStageNames.delete(activeGraphStageName);
        }
        activeGraphStageName = stageName;
        runningStageNames.add(stageName);
        completedStageNames.delete(stageName);
        if (tr.firstStartedAt === null) tr.firstStartedAt = timestamp;
        tr.lastInvocationStart = timestamp;
        tr.endedAt = null;
      } else {
        closeRunningTools(timestamp);
        completedStageNames.add(stageName);
        runningStageNames.delete(stageName);
        if (tr.lastInvocationStart !== null) {
          tr.totalDurationMs += Math.max(
            10,
            timestamp - tr.lastInvocationStart
          );
          tr.lastInvocationStart = null;
        }
        tr.endedAt = timestamp;
        if (activeGraphStageName === stageName) {
          activeGraphStageName = null;
        }
      }
      continue;
    }

    // kind === "tool"
    if (type === "start") {
      runningStageNames.add(stageName);
      runningToolNames.add(stageName);
      if (tr.firstStartedAt === null) tr.firstStartedAt = timestamp;
      tr.lastInvocationStart = timestamp;
      tr.endedAt = null;
    } else {
      completedStageNames.add(stageName);
      runningStageNames.delete(stageName);
      runningToolNames.delete(stageName);
      if (tr.lastInvocationStart !== null) {
        tr.totalDurationMs += Math.max(
          MIN_STAGE_DURATION_MS,
          timestamp - tr.lastInvocationStart
        );
        tr.lastInvocationStart = null;
      }
      tr.endedAt = timestamp;
    }
  }

  // Final sanity check: If flow reached completion or ChatOutput ran, close lingering stages/tools
  const hasFinished =
    completedStageNames.has("ChatOutput") ||
    packets.some(
      (p) =>
        p.obj?.type === PacketType.STOP ||
        (p.obj?.type === PacketType.GRAPH_STAGE_END &&
          typeof p.obj?.stage_name === "string" &&
          p.obj.stage_name.toLowerCase().includes("output"))
    );

  if (hasFinished) {
    const finalTs = packetTimestamps[packetTimestamps.length - 1] ?? Date.now();
    closeRunningTools(finalTs);
    if (activeGraphStageName) {
      const prevTr = getTracker(activeGraphStageName);
      if (prevTr.lastInvocationStart !== null) {
        prevTr.totalDurationMs += Math.max(
          10,
          finalTs - prevTr.lastInvocationStart
        );
        prevTr.lastInvocationStart = null;
      }
      prevTr.endedAt = finalTs;
      completedStageNames.add(activeGraphStageName);
      runningStageNames.delete(activeGraphStageName);
    }
  }

  const stageTimings = new Map<string, StageTiming>();
  for (const [name, tr] of Array.from(trackerMap.entries())) {
    stageTimings.set(name, {
      startedAt: tr.firstStartedAt,
      endedAt: tr.endedAt,
      durationMs: tr.totalDurationMs > 0 ? tr.totalDurationMs : null,
    });
  }

  return { runningStageNames, completedStageNames, stageTimings };
}

export function getCallSequence(
  packets: Packet[],
  stageDefinitions: StageDefinition[],
  toolNameToNodeId: Map<string, string>,
  toolNodeIdToAgentNodeId: Map<string, string>,
  progress: StageProgress,
  packetTimestamps: number[] = []
): CallEntry[] {
  const stageByMatchName = new Map<string, StageDefinition>(
    stageDefinitions.map((s) => [s.matchName, s])
  );
  const knownStageNames = new Set(
    stageDefinitions.map((stage) => stage.matchName)
  );
  const sequence: CallEntry[] = [];
  const entryIndexByMatchName = new Map<string, number>();
  let activeGraphMatchName: string | null = null;

  for (let i = 0; i < packets.length; i++) {
    const packet = packets[i];
    if (!packet) continue;
    const ts = packetTimestamps[i] ?? Date.now();
    const event = resolveStageEvent(packet, toolNameToNodeId, ts);
    if (!event) continue;
    const { type, stageName, kind, timestamp, callId, parentStageNodeId } =
      event;

    if (
      stageDefinitions.length > 0 &&
      !knownStageNames.has(stageName) &&
      kind === "graph"
    ) {
      continue;
    }

    const def = stageByMatchName.get(stageName);
    const label = def?.label ?? prettifyNodeId(stageName);

    if (kind === "tool") {
      // Find the best parent stage to attribute this tool to:
      let parentStage: CallEntry | undefined;

      // 1. Exact: the backend stamped the running stage's node id on the
      //    packet (`stage_node_id`). No guessing — this is the stage that
      //    actually made the call, and it survives a reload.
      if (parentStageNodeId) {
        const stageIdx = entryIndexByMatchName.get(parentStageNodeId);
        if (stageIdx !== undefined) parentStage = sequence[stageIdx];
      }

      // 2. If currently streaming within an active graph stage:
      if (!parentStage && activeGraphMatchName) {
        const stageIdx = entryIndexByMatchName.get(activeGraphMatchName);
        if (stageIdx !== undefined) parentStage = sequence[stageIdx];
      }

      // 3. Legacy fallback (runs persisted before `stage_node_id`): the
      //    tool node's own graph edge into an agent stage.
      if (!parentStage && toolNodeIdToAgentNodeId) {
        const targetNodeId = toolNodeIdToAgentNodeId.get(stageName);
        if (targetNodeId) {
          parentStage = sequence.find(
            (e) =>
              e.matchName === targetNodeId || e.key.startsWith(targetNodeId)
          );
        }
      }

      // 4. Legacy fallback: the tool's timestamp falls inside a stage's
      //    recorded start/end window.
      if (!parentStage && timestamp > 0) {
        for (const entry of sequence) {
          const timing = progress.stageTimings.get(entry.matchName);
          if (
            timing &&
            timing.startedAt !== null &&
            timing.endedAt !== null &&
            timestamp >= timing.startedAt &&
            timestamp <= timing.endedAt
          ) {
            parentStage = entry;
            break;
          }
        }
      }

      // 5. Legacy fallback: first non-I/O agent stage.
      if (!parentStage) {
        parentStage = sequence.find((e) => !NON_STAGE_NODE_TYPES.has(e.label));
      }

      // If parent stage found, embed the tool badge inside that stage!
      if (parentStage) {
        if (!parentStage.tools) parentStage.tools = [];
        const existingTool = parentStage.tools.find(
          (t) => t.toolName === stageName || t.label === label
        );
        if (existingTool) {
          if (type === "start") {
            existingTool.callCount += 1;
            existingTool.status = "running";
            existingTool.invocations.push({
              index: existingTool.invocations.length + 1,
              callId,
              startedAt: timestamp > 0 ? timestamp : null,
              endedAt: null,
              durationMs: null,
            });
          } else {
            existingTool.status = "done";
            let openInv: ToolInvocation | undefined;
            if (callId) {
              openInv = existingTool.invocations.find(
                (inv) => inv.callId === callId && inv.endedAt === null
              );
            }
            if (!openInv) {
              openInv = [...existingTool.invocations]
                .reverse()
                .find((inv) => inv.endedAt === null);
            }
            if (openInv) {
              openInv.endedAt = timestamp > 0 ? timestamp : null;
              if (openInv.startedAt !== null && timestamp > openInv.startedAt) {
                openInv.durationMs = Math.max(
                  MIN_STAGE_DURATION_MS,
                  timestamp - openInv.startedAt
                );
              }
            }
          }
        } else {
          parentStage.tools.push({
            toolName: stageName,
            label,
            callCount: 1,
            durationMs: null,
            status: type === "start" ? "running" : "done",
            invocations: [
              {
                index: 1,
                callId,
                startedAt: timestamp > 0 ? timestamp : null,
                endedAt:
                  type === "end" ? (timestamp > 0 ? timestamp : null) : null,
                durationMs: null,
              },
            ],
          });
        }
      } else if (sequence.length === 0) {
        // Only if there are NO graph stages at all (classic single-agent standalone tool)
        const existingIdx = entryIndexByMatchName.get(stageName);
        if (existingIdx !== undefined && sequence[existingIdx]) {
          if (type === "start") {
            sequence[existingIdx]!.callCount += 1;
          }
          sequence[existingIdx]!.status = progress.runningStageNames.has(
            stageName
          )
            ? "running"
            : "done";
        } else {
          const newIdx = sequence.length;
          sequence.push({
            key: `${stageName}-${newIdx}`,
            matchName: stageName,
            label,
            status: progress.runningStageNames.has(stageName)
              ? "running"
              : "done",
            callCount: 1,
            durationMs: null,
            isResource: true,
          });
          entryIndexByMatchName.set(stageName, newIdx);
        }
      }
      continue;
    }

    // kind === "graph"
    if (type === "start") {
      if (activeGraphMatchName && activeGraphMatchName !== stageName) {
        const prevIdx = entryIndexByMatchName.get(activeGraphMatchName);
        if (prevIdx !== undefined && sequence[prevIdx]) {
          sequence[prevIdx]!.status = "done";
        }
      }

      const existingIdx = entryIndexByMatchName.get(stageName);
      const existingEntry =
        existingIdx !== undefined ? sequence[existingIdx] : undefined;
      if (existingEntry && activeGraphMatchName === stageName) {
        existingEntry.status = progress.runningStageNames.has(stageName)
          ? "running"
          : "done";
      } else if (
        existingIdx !== undefined &&
        activeGraphMatchName !== stageName
      ) {
        const newIdx = sequence.length;
        sequence.push({
          key: `${stageName}-${newIdx}`,
          matchName: stageName,
          label,
          status: "running",
          callCount: (sequence[existingIdx]?.callCount || 1) + 1,
          durationMs: null,
        });
        entryIndexByMatchName.set(stageName, newIdx);
      } else {
        const newIdx = sequence.length;
        sequence.push({
          key: `${stageName}-${newIdx}`,
          matchName: stageName,
          label,
          status: "running",
          callCount: 1,
          durationMs: null,
        });
        entryIndexByMatchName.set(stageName, newIdx);
      }
      activeGraphMatchName = stageName;
    } else {
      const idx = entryIndexByMatchName.get(stageName);
      if (idx !== undefined && sequence[idx]) {
        sequence[idx]!.status = "done";
      }
      if (activeGraphMatchName === stageName) {
        activeGraphMatchName = null;
      }
    }
  }

  // Update status and duration for all entries from progress
  sequence.forEach((entry, i) => {
    if (entryIndexByMatchName.get(entry.matchName) === i) {
      if (progress.completedStageNames.has(entry.matchName)) {
        entry.status = "done";
      } else if (progress.runningStageNames.has(entry.matchName)) {
        entry.status = "running";
      }
    }
    const timing = progress.stageTimings.get(entry.matchName);
    entry.durationMs = timing?.durationMs ?? null;

    if (entry.tools) {
      entry.tools.forEach((tool) => {
        const toolTiming = progress.stageTimings.get(tool.toolName);
        if (progress.completedStageNames.has(tool.toolName)) {
          tool.status = "done";
        }

        // Sum up known durations from individual invocations
        const knownSum = tool.invocations.reduce(
          (acc, inv) => acc + (inv.durationMs || 0),
          0
        );

        if (knownSum > 0) {
          tool.durationMs = knownSum;
        } else if (toolTiming?.durationMs) {
          tool.durationMs = toolTiming.durationMs;
        }

        // Only for invocations that truly have no recorded duration, assign a fallback
        const total = tool.durationMs || 10;
        const missingInvs = tool.invocations.filter((inv) => !inv.durationMs);
        if (missingInvs.length > 0) {
          const remainingTime = Math.max(
            MIN_STAGE_DURATION_MS * missingInvs.length,
            total - knownSum
          );
          const avg = Math.max(
            MIN_STAGE_DURATION_MS,
            Math.round(remainingTime / missingInvs.length)
          );
          missingInvs.forEach((inv) => {
            inv.durationMs = avg;
          });
        }
      });
    }
  });

  // Append any not-yet-called stage definitions as pending at the end
  const calledMatchNames = new Set(sequence.map((entry) => entry.matchName));
  const pending: CallEntry[] = stageDefinitions
    .filter(
      (stage) =>
        !calledMatchNames.has(stage.matchName) &&
        !stage.isResource &&
        !isConfigNode(stage.matchName) &&
        !isConfigNode(stage.label)
    )
    .map((stage) => ({
      key: `${stage.matchName}-pending`,
      matchName: stage.matchName,
      label: stage.label,
      status: "pending",
      callCount: 1,
      durationMs: null,
    }));

  return [...sequence, ...pending];
}

/** The published flow version_no this run actually executed, taken from the
 * `flow_version` packet the backend emits once per FlowAgent run (and
 * replays on reload). `null` for runs that predate version pinning — the
 * strip then falls back to the currently published flow. */
export function flowVersionNoFromPackets(packets: Packet[]): number | null {
  for (const packet of packets) {
    const obj = packet?.obj as
      | { type?: unknown; version_no?: unknown }
      | undefined;
    if (
      obj?.type === PacketType.FLOW_VERSION &&
      typeof obj.version_no === "number"
    ) {
      return obj.version_no;
    }
  }
  return null;
}

export function buildNodeRunStatus(
  progress: StageProgress
): Record<string, NodeRunStatus> {
  const result: Record<string, NodeRunStatus> = {};

  for (const name of Array.from(progress.completedStageNames)) {
    const timing = progress.stageTimings.get(name);
    result[name] = {
      status: "done",
      startedAt: timing?.startedAt ?? null,
      endedAt: timing?.endedAt ?? null,
      durationMs: timing?.durationMs ?? null,
      tokenCount: null,
    };
  }

  for (const name of Array.from(progress.runningStageNames)) {
    const timing = progress.stageTimings.get(name);
    result[name] = {
      status: "running",
      startedAt: timing?.startedAt ?? null,
      endedAt: null,
      durationMs: null,
      tokenCount: null,
    };
  }

  return result;
}
