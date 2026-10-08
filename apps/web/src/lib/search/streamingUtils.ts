import { PacketType } from "@/lib/api/domains/chat/message-types";
import {
  isRunMetaPacket,
  type RunMetaPacket,
} from "@/lib/api/domains/chat/run-types";
import {
  GENERATED_FILE_CATEGORY_ID,
  TOOL_PACKET_TYPES,
  getCategoryFor,
  shouldSplitCategories,
} from "./packetCategories";

export interface SSEStreamOptions {
  /** Parse but do not yield events whose id is <= this (replay after a re-attach). */
  suppressThroughSeq?: number;
  /** Called at each event boundary, after that event's packets were yielded. */
  onEventId?: (seq: number) => void;
  /** Receives run meta packets; they are never yielded and never touch turn bookkeeping. */
  onRunMeta?: (meta: RunMetaPacket) => void;
}

// Backend packet types from our agent-service
interface BackendPacket {
  type: string;
  content?: any;
  error?: { code: string; message: string };
  // Set on graph_stage_start / graph_stage_end packets (flow-canvas node
  // execution boundaries streamed to the chat flow preview).
  stage_name?: string;
  // Set on flow_stage_* and stage-scoped reasoning/tool packets (FlowAgent
  // per-stage timeline).
  stage_key?: string;
  stage_order?: number;
  iteration?: number;
  is_final_stage?: boolean;
  // Structurally known (before this run proves it) to sit on a Loop/While
  // cycle — lets the timeline fold iteration one into its collapsible group
  // right away instead of flashing it as a standalone card. See B18.
  is_loop_body?: boolean;
}

function extractMessageContent(content: any): string {
  if (typeof content === "string") {
    return content;
  }

  if (typeof content !== "object" || content === null) {
    return "";
  }

  if (content.content !== undefined) {
    if (typeof content.content === "string") {
      return content.content;
    }

    if (Array.isArray(content.content)) {
      for (const item of content.content) {
        if (typeof item === "object" && item?.type === "text") {
          return item.text || "";
        }
      }
    }
  }

  return "";
}

// Map backend packets to frontend PacketType
function mapBackendToFrontend(packet: BackendPacket): any {
  const defaultPlacement = { turn_index: 0, sub_turn_index: null };

  switch (packet.type) {
    case "message":
      // Full message from providers that do not stream tokens.
      return {
        placement: defaultPlacement,
        obj: {
          type: "message_delta",
          content: extractMessageContent(packet.content),
        },
      };

    case "token":
      // Token chunk - convert to message_delta
      // Extract token content from potentially nested structure
      let tokenContent = "";
      const tokenData = packet.content;
      if (typeof tokenData === "string") {
        tokenContent = tokenData;
      } else if (typeof tokenData === "object" && tokenData !== null) {
        // Handle nested token format
        if (tokenData.text) {
          tokenContent = tokenData.text;
        } else if (tokenData.content) {
          tokenContent =
            typeof tokenData.content === "string" ? tokenData.content : "";
        }
      }

      return {
        placement: defaultPlacement,
        obj: {
          type: "message_delta",
          content: tokenContent,
        },
      };

    case "error":
      return {
        placement: defaultPlacement,
        error: packet.error?.message || packet.content || "Unknown error",
        stack_trace: "",
      };

    case "stop":
      return {
        placement: defaultPlacement,
        obj: {
          type: "stop",
          stop_reason: "finished",
        },
      };

    // Tool lifecycle packets — pass through directly for AgentTimeline
    case "custom_tool_start":
    case "custom_tool_delta":
    case "search_tool_start":
    case "search_tool_queries_delta":
    case "search_tool_documents_delta":
    case "open_url_start":
    case "open_url_urls":
    case "open_url_documents":
    case "python_tool_start":
    case "python_tool_delta":
    case "file_reader_start":
    case "file_reader_result":
    case "memory_tool_start":
    case "memory_tool_delta":
    case "memory_tool_no_access":
    case "deep_research_plan_start":
    case "deep_research_plan_delta":
    case "research_agent_start":
    case "intermediate_report_start":
    case "intermediate_report_delta":
    case "intermediate_report_cited_docs":
      return {
        placement: defaultPlacement,
        obj: packet,
      };

    // Step lifecycle packets — each step becomes a new turn group in the timeline.
    // We map custom_step_start to a custom_tool_start so the existing timeline
    // renderer shows it as a named section without any additional frontend changes.
    case "custom_step_start":
      return {
        placement: defaultPlacement,
        obj: {
          type: "custom_tool_start",
          tool_name: `[step] ${(packet as any).step_name ?? "step"}`,
        },
      };

    // Flow-canvas node execution boundaries (chat's flow preview panel) —
    // not rendered in the AgentTimeline, just consumed by the chat-flow
    // preview store; passed through as-is like reasoning_start/delta below.
    case "graph_stage_start":
    case "graph_stage_end":
      return {
        placement: defaultPlacement,
        obj: { type: packet.type, stage_name: packet.stage_name },
      };

    case "reasoning_start":
      return {
        placement: defaultPlacement,
        obj: { type: "reasoning_start" },
      };

    case "reasoning_delta":
      return {
        placement: defaultPlacement,
        obj: {
          type: "reasoning_delta",
          reasoning: (packet as any).reasoning ?? "",
        },
      };

    default:
      // Unknown packet type - return as-is wrapped
      return {
        placement: defaultPlacement,
        obj: packet,
      };
  }
}

const CALL_START_TYPES = new Set<string>([
  "custom_tool_start",
  "open_url_start",
  "python_tool_start",
  "file_reader_start",
  "memory_tool_start",
  "deep_research_plan_start",
  "research_agent_start",
]);

export async function* handleSSEStream<T extends PacketType>(
  streamingResponse: Response,
  signal?: AbortSignal,
  options: SSEStreamOptions = {}
): AsyncGenerator<T, void, unknown> {
  const reader = streamingResponse.body?.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  // The id of the SSE event whose data lines are currently being parsed.
  // Cleared at each event boundary (blank line).
  let currentSeq: number | null = null;
  // The id of the last event whose data line was fully handled. Only this id
  // is ever reported: an event whose data never arrived (or arrived cut off)
  // must be replayed, and one already yielded must not be.
  let handledSeq: number | null = null;
  const reportHandledSeq = () => {
    if (handledSeq !== null) {
      options.onEventId?.(handledSeq);
      handledSeq = null;
    }
  };

  // Track turn_index so tool packets and message packets land in separate groups.
  // The frontend packetProcessor classifies an entire group by its *first* packet,
  // so tool packets must have a different turn_index than message/display packets.
  let turnIndex = 0;
  // The turn an ask_user card was placed on, so the packet that locks it
  // lands in the same display group instead of opening one of its own.
  let lastClarificationTurn: number | null = null;
  let sawToolPackets = false;
  let lastToolPacketType: string | null = null;
  // A single AI turn can fire several calls to the same tool at once (e.g.
  // parallel web_search/fetch_webpage calls): all their start packets arrive before
  // any result comes back, so by the time a call's own delta/documents show up,
  // turnIndex has already moved on to later calls. Each call's turn is
  // remembered here by call_id — like `documentTurnIndex` below — so its delta is
  // placed back on its own turn instead of whatever turn happens to be current.
  const toolCallTurns = new Map<string, number>();
  // If tokens were already streamed for the current answer, skip the later
  // full "message" packet from backend to avoid duplicate text rendering.
  let sawTokenForCurrentAnswer = false;
  let hasMessageStartForCurrentAnswer = false;
  // Turn index of the document generation currently in flight. Its progress
  // packets and the resulting file must share one group even if the model
  // interleaves answer text, otherwise the skeleton would never be replaced.
  let documentTurnIndex: number | null = null;

  if (signal) {
    signal.addEventListener("abort", () => {
      reader?.cancel();
    });
    // An already-aborted signal never fires the listener: cancel now so a
    // pending read cannot hang the stream.
    if (signal.aborted) reader?.cancel();
  }

  if (!reader) {
    throw new Error("No reader available for stream");
  }

  // A replayed packet is parsed (the turn/tool bookkeeping must see the whole
  // stream) but not yielded. `emit` is the one place that decides.
  let suppressed = false;
  function* emit(packet: T): Generator<T, void, unknown> {
    if (!suppressed) yield packet;
  }

  try {
    while (true) {
      const rawChunk = await reader.read();
      if (rawChunk.done) {
        break;
      }

      const { value } = rawChunk;
      if (!value) continue;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.trim() === "") {
          reportHandledSeq();
          currentSeq = null;
          continue;
        }

        const trimmedLine = line.trim();
        if (trimmedLine.startsWith("id:")) {
          const seq = Number.parseInt(trimmedLine.slice(3).trim(), 10);
          currentSeq = Number.isFinite(seq) ? seq : null;
          continue;
        }
        if (trimmedLine.startsWith(":")) {
          continue;
        }
        suppressed =
          currentSeq !== null &&
          currentSeq <= (options.suppressThroughSeq ?? 0);
        // Lines are only split off the buffer once complete, so this data
        // line is handled in full (every packet it maps to is yielded before
        // the next read).
        if (currentSeq !== null) handledSeq = currentSeq;
        if (
          trimmedLine === "data: [DONE]" ||
          trimmedLine === "[DONE]" ||
          trimmedLine === "data:"
        ) {
          yield* emit({
            placement: { turn_index: turnIndex, sub_turn_index: null },
            obj: { type: "stop", stop_reason: "finished" },
          } as T);
          continue;
        }

        let jsonLine = line;
        if (line.startsWith("data: ")) {
          jsonLine = line.slice(6);
        }

        try {
          const backendPacket = JSON.parse(jsonLine) as BackendPacket;

          // Run lifecycle meta packets: never rendered, never yielded, and
          // they never touch the turn/tool bookkeeping below.
          if (isRunMetaPacket(backendPacket)) {
            options.onRunMeta?.(backendPacket);
            continue;
          }

          // The real, persisted ids for this turn — sent once, near the end
          // of the stream, with no `type` field. It's pure metadata, not a
          // display packet, so it must reach the consumer exactly as sent
          // (matching MessageResponseIDInfo) instead of falling through to
          // the generic default case below, which would wrap it as
          // `{ obj: packet }` and leave `packet.user_message_id` /
          // `packet.reserved_assistant_message_id` unreadable at the top
          // level where useChatController.ts checks for them. It must also
          // skip the turn/tool-tracking logic below — it carries no display
          // content and would otherwise perturb turnIndex bookkeeping.
          if (
            "reserved_assistant_message_id" in backendPacket ||
            "user_message_id" in backendPacket
          ) {
            yield* emit(backendPacket as unknown as T);
            continue;
          }

          // FlowAgent per-stage timeline markers. They carry no answer-bubble
          // content and must not perturb the turn/tool bookkeeping below —
          // the AgentTimeline's stage-grouping layer reads them straight from
          // placement. `stage_key` etc. ride in placement so packetProcessor
          // can bucket a stage's reasoning/tool/output packets without
          // inspecting obj.
          if (
            backendPacket.type === "flow_stage_start" ||
            backendPacket.type === "flow_stage_end" ||
            backendPacket.type === "flow_stage_output_delta"
          ) {
            yield* emit({
              placement: {
                turn_index: turnIndex,
                sub_turn_index: null,
                stage_key: (backendPacket as any).stage_key,
                stage_order: (backendPacket as any).stage_order,
                iteration: (backendPacket as any).iteration,
                is_final_stage: (backendPacket as any).is_final_stage,
                is_loop_body: (backendPacket as any).is_loop_body,
              },
              obj: backendPacket,
            } as T);
            continue;
          }

          // A run pausing at a HumanInput node is its own display group: the
          // prompt + its buttons must not be swallowed by the answer group
          // that precedes it (findRenderer would hand a mixed group to the
          // text renderer and the buttons would never appear). Give it a
          // fresh turn, and leave the next packet on a fresh one too.
          if (
            backendPacket.type === "human_input" ||
            backendPacket.type === "user_clarification"
          ) {
            turnIndex++;
            const humanInputTurn = turnIndex;
            lastClarificationTurn = humanInputTurn;
            turnIndex++;
            sawToolPackets = false;
            lastToolPacketType = null;
            sawTokenForCurrentAnswer = false;
            hasMessageStartForCurrentAnswer = false;
            yield* emit({
              placement: { turn_index: humanInputTurn, sub_turn_index: null },
              obj: backendPacket,
            } as T);
            continue;
          }

          // The lock belongs to the card it locks, not to a turn of its
          // own: split them and the group reaches the wrong renderer and
          // the answers never show.
          if (
            backendPacket.type === "user_clarification_answered" &&
            lastClarificationTurn !== null
          ) {
            yield* emit({
              placement: {
                turn_index: lastClarificationTurn,
                sub_turn_index: null,
              },
              obj: backendPacket,
            } as T);
            continue;
          }

          if (backendPacket.type === "token") {
            sawTokenForCurrentAnswer = true;
          }

          if (backendPacket.type === "message" && sawTokenForCurrentAnswer) {
            // Token stream already provided this answer incrementally.
            // Skip duplicated full-message payload.
            continue;
          }

          // Drop step-start events for internal infrastructure nodes (e.g. "model", "agent", "tools")
          // so that normal agent iterations never render confusing "[step] model" timeline cards.
          if (
            backendPacket.type === "custom_step_start" &&
            [
              "model",
              "agent",
              "tools",
              "call_model",
              "__start__",
              "__end__",
              "__interrupt__",
            ].includes((backendPacket as any).step_name)
          ) {
            continue;
          }

          // Advance turn_index at both transitions (display→tool and tool→display)
          // so each section lands in its own group for the packetProcessor.
          //
          // Document packets are deliberately exempt: a model often starts its
          // tool call mid-sentence, and treating that as a tool boundary would
          // cut the answer in half (sometimes mid-word) around the file card.
          // They ride the current turn and get their own group from the
          // "genfile" group suffix instead, so the card renders after the text.
          const isGeneratedFilePkt =
            getCategoryFor(backendPacket.type)?.id ===
            GENERATED_FILE_CATEGORY_ID;
          const isReasoningPkt =
            backendPacket.type === "reasoning_start" ||
            backendPacket.type === "reasoning_delta";
          const isMidAnswerReasoningPkt =
            isReasoningPkt && sawTokenForCurrentAnswer;
          const isToolPkt =
            TOOL_PACKET_TYPES.has(backendPacket.type) &&
            !isGeneratedFilePkt &&
            !isMidAnswerReasoningPkt;
          if (isGeneratedFilePkt || isMidAnswerReasoningPkt) {
            // Document generation packets ride the current turn (or documentTurnIndex)
            // without breaking tool or display pacing state. Same for mid-answer
            // reasoning packets — see comment above.
          } else if (isToolPkt) {
            const callId = (backendPacket as any).call_id ?? null;
            const isCallStartType = CALL_START_TYPES.has(backendPacket.type);
            const isNewCallStart =
              isCallStartType &&
              ((callId && !toolCallTurns.has(callId)) ||
                (!callId && lastToolPacketType !== null));
            if (!sawToolPackets) {
              turnIndex++; // display → tool: pre-tool text gets its own group
              sawTokenForCurrentAnswer = false;
              hasMessageStartForCurrentAnswer = false;
            } else if (isNewCallStart) {
              turnIndex++;
              sawTokenForCurrentAnswer = false;
              hasMessageStartForCurrentAnswer = false;
            } else if (
              lastToolPacketType &&
              shouldSplitCategories(lastToolPacketType, backendPacket.type)
            ) {
              turnIndex++;
              sawTokenForCurrentAnswer = false;
              hasMessageStartForCurrentAnswer = false;
            }
            sawToolPackets = true;
            lastToolPacketType = backendPacket.type;
            if (callId && !toolCallTurns.has(callId)) {
              toolCallTurns.set(callId, turnIndex);
            }
          } else if (sawToolPackets) {
            turnIndex++;
            sawToolPackets = false;
            lastToolPacketType = null;
            sawTokenForCurrentAnswer = false;
            hasMessageStartForCurrentAnswer = false;
          }

          if (backendPacket.type === "token") {
            sawTokenForCurrentAnswer = true;
          }

          if (backendPacket.type === "stop") {
            sawTokenForCurrentAnswer = false;
            hasMessageStartForCurrentAnswer = false;
          }

          if (backendPacket.type === "message_start") {
            const duration = (backendPacket as any)
              .pre_answer_processing_seconds;
            yield* emit({
              placement: { turn_index: turnIndex, sub_turn_index: null },
              obj: {
                type: "message_start",
                content: "",
                final_documents: null,
                pre_answer_processing_seconds: duration,
              },
            } as T);
            hasMessageStartForCurrentAnswer = true;
            continue;
          }

          if (
            backendPacket.type === "token" &&
            !hasMessageStartForCurrentAnswer
          ) {
            yield* emit({
              placement: { turn_index: turnIndex, sub_turn_index: null },
              obj: {
                type: "message_start",
                content: "",
                final_documents: null,
              },
            } as T);
            hasMessageStartForCurrentAnswer = true;
          }

          if (
            backendPacket.type === "message" &&
            !hasMessageStartForCurrentAnswer
          ) {
            const duration = (backendPacket as any).content?.additional_kwargs
              ?.processing_duration_seconds;
            yield* emit({
              placement: { turn_index: turnIndex, sub_turn_index: null },
              obj: {
                type: "message_start",
                content: "",
                final_documents: null,
                pre_answer_processing_seconds: duration,
              },
            } as T);
            hasMessageStartForCurrentAnswer = true;
          }

          const mappedPacket = mapBackendToFrontend(backendPacket);

          // A stage-scoped reasoning/tool packet carries its stage identity so
          // the timeline nests it under the right numbered stage group. Spread
          // to a fresh placement — mapBackendToFrontend hands back a shared
          // object for several packet types.
          if ((backendPacket as any).stage_key !== undefined) {
            mappedPacket.placement = {
              ...mappedPacket.placement,
              stage_key: (backendPacket as any).stage_key,
              stage_order: (backendPacket as any).stage_order,
              iteration: (backendPacket as any).iteration,
            };
          }

          if (backendPacket.type === "document_generation_start") {
            documentTurnIndex = turnIndex;
          }
          const packetCallId = (backendPacket as any).call_id ?? null;
          mappedPacket.placement.turn_index =
            isGeneratedFilePkt && documentTurnIndex !== null
              ? documentTurnIndex
              : packetCallId && toolCallTurns.has(packetCallId)
                ? toolCallTurns.get(packetCallId)!
                : turnIndex;
          if (
            backendPacket.type === "document_generation_end" &&
            (backendPacket as any).status === "success"
          ) {
            // A failed attempt keeps the turn pinned: the agent is told to fix
            // its tool call and retry, and that retry belongs in the same slot
            // so its result replaces the failure instead of stacking under it.
            documentTurnIndex = null;
          }

          yield* emit(mappedPacket as T);
        } catch (error) {
          console.error("Error parsing SSE data:", error);
        }
      }
    }
  } catch (error) {
    console.error("Stream error:", error);
    throw error;
  } finally {
    // A stream can end, or fail, right after an event's data line and before
    // its blank line: that event was still delivered.
    reportHandledSeq();
  }
}
