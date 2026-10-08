import {
  CustomToolDelta,
  CustomToolStart,
  Packet,
  PacketType,
} from "@/lib/api/domains/chat/streaming-types";
import {
  KNOWLEDGE_RESPONSE_TYPE,
  KnowledgeEvidence,
  parseKnowledgeEvidence,
} from "@/lib/api/domains/chat/knowledge-evidence-types";
import { KNOWLEDGE_TOOL_NAMES } from "@/lib/tools/knowledgeToolNames";

/**
 * Flow retrieval components, by the tool a search of theirs is named like. A
 * tool-mode component is called by its node id (`DocumentSearch-a1b2`).
 */
const KNOWLEDGE_COMPONENT_TOOLS: ReadonlyMap<string, string> = new Map([
  ["DocumentSearch", "document_search"],
  ["KnowledgeBase", "document_search"],
  ["GraphSearch", "graph_search"],
  ["GraphEntitySearch", "graph_entity_search"],
  ["GraphNeighborhood", "graph_neighborhood"],
]);
const COMPONENT_NODE_ID = /^([A-Za-z]+)-[A-Za-z0-9]+$/;

/** The knowledge tool a call's name stands for, or ``null`` for any other tool. */
function knowledgeToolFor(toolName: string): string | null {
  if (KNOWLEDGE_TOOL_NAMES.has(toolName)) return toolName;
  const component = COMPONENT_NODE_ID.exec(toolName)?.[1];
  return (component && KNOWLEDGE_COMPONENT_TOOLS.get(component)) || null;
}

export type KnowledgeCallStatus = "running" | "done" | "unavailable";

export interface KnowledgeCall {
  callId: string | null;
  toolName: string;
  query: string;
  status: KnowledgeCallStatus;
  evidence: KnowledgeEvidence | null;
  /** The tool's own text when it returned no evidence (e.g. an error). */
  fallbackText: string | null;
}

export function isKnowledgePacket(packet: Packet): boolean {
  const obj = packet.obj;
  if (obj.type === PacketType.CUSTOM_TOOL_DELTA) {
    return (obj as CustomToolDelta).response_type === KNOWLEDGE_RESPONSE_TYPE;
  }
  if (obj.type === PacketType.CUSTOM_TOOL_START) {
    return knowledgeToolFor((obj as CustomToolStart).tool_name) !== null;
  }
  return false;
}

function queryFromArgs(args: CustomToolStart["args"]): string {
  if (args && typeof args === "object" && typeof args.query === "string") {
    return args.query;
  }
  return "";
}

function textOf(data: unknown): string | null {
  if (data === undefined || data === null || data === "") return null;
  return typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

function applyResult(call: KnowledgeCall, delta: CustomToolDelta): void {
  if (delta.response_type !== KNOWLEDGE_RESPONSE_TYPE) {
    call.status = "done";
    call.fallbackText = textOf(delta.data);
    return;
  }
  call.evidence = parseKnowledgeEvidence(delta.data);
  call.status = call.evidence ? "done" : "unavailable";
  if (call.evidence && !call.query) call.query = call.evidence.query;
}

/**
 * One entry per knowledge call in a packet group. Results are matched to
 * their call by `call_id`, so parallel calls whose results arrive out of
 * order still pair correctly.
 */
export function constructKnowledgeCalls(packets: Packet[]): KnowledgeCall[] {
  const calls: KnowledgeCall[] = [];
  const byId = new Map<string, KnowledgeCall>();

  for (const packet of packets) {
    const obj = packet.obj;
    if (obj.type === PacketType.CUSTOM_TOOL_START) {
      const start = obj as CustomToolStart;
      const call: KnowledgeCall = {
        callId: start.call_id ?? null,
        toolName: start.tool_name,
        query: queryFromArgs(start.args),
        status: "running",
        evidence: null,
        fallbackText: null,
      };
      calls.push(call);
      if (call.callId) byId.set(call.callId, call);
    } else if (obj.type === PacketType.CUSTOM_TOOL_DELTA) {
      const delta = obj as CustomToolDelta;
      const callId = delta.call_id ?? null;
      let call =
        (callId && byId.get(callId)) ||
        (!callId ? calls.findLast((c) => c.status === "running") : undefined);
      if (!call) {
        call = {
          callId,
          toolName: delta.tool_name,
          query: "",
          status: "running",
          evidence: null,
          fallbackText: null,
        };
        calls.push(call);
        if (callId) byId.set(callId, call);
      }
      applyResult(call, delta);
    }
  }
  return calls;
}

const GRAPH_TOOL_NAMES: ReadonlySet<string> = new Set([
  "graph_search",
  "graph_entity_search",
  "graph_neighborhood",
]);

/** Whether the call searched the knowledge graph (by result, else by tool). */
export function isGraphCall(call: KnowledgeCall): boolean {
  if (call.evidence) return call.evidence.kind === "graph";
  return GRAPH_TOOL_NAMES.has(knowledgeToolFor(call.toolName) ?? "");
}
