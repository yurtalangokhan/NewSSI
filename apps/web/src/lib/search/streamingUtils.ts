import { PacketType } from "@/app/app/services/lib";
import {
  GENERATED_FILE_CATEGORY_ID,
  TOOL_PACKET_TYPES,
  getCategoryFor,
  shouldSplitCategories,
} from "./packetCategories";

// Backend packet types from our agent-service
interface BackendPacket {
  type: string;
  content?: any;
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
          tokenContent = typeof tokenData.content === "string" ? tokenData.content : "";
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
        error: packet.content || "Unknown error",
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


export async function* handleSSEStream<T extends PacketType>(
  streamingResponse: Response,
  signal?: AbortSignal
): AsyncGenerator<T, void, unknown> {
  const reader = streamingResponse.body?.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // Track turn_index so tool packets and message packets land in separate groups.
  // The frontend packetProcessor classifies an entire group by its *first* packet,
  // so tool packets must have a different turn_index than message/display packets.
  let turnIndex = 0;
  let sawToolPackets = false;
  let lastToolPacketType: string | null = null;
  // A single AI turn can fire several calls to the same tool at once (e.g.
  // parallel web_search calls): all their `custom_tool_start`s arrive before
  // any result comes back, so by the time a call's own `custom_tool_delta`
  // shows up, turnIndex has already moved on to later calls. Each call's
  // turn is remembered here by call_id — like `documentTurnIndex` below —
  // so its delta is placed back on its own turn instead of whatever turn
  // happens to be current when it arrives.
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
  }
  
  if (!reader) {
    throw new Error("No reader available for stream");
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
        if (line.trim() === "") continue;

        const trimmedLine = line.trim();
        // SSE comment (": keep-alive") — the backend sends these so proxies
        // don't treat a long silent generation as an idle connection. They
        // carry no packet, so drop them before the JSON parse below.
        if (trimmedLine.startsWith(":")) {
          continue;
        }
        if (trimmedLine === "data: [DONE]" || trimmedLine === "[DONE]" || trimmedLine === "data:") {
          yield {
            placement: { turn_index: turnIndex, sub_turn_index: null },
            obj: { type: "stop", stop_reason: "finished" },
          } as T;
          continue;
        }

        let jsonLine = line;
        if (line.startsWith("data: ")) {
          jsonLine = line.slice(6);
        }

        try {
          const backendPacket = JSON.parse(jsonLine) as BackendPacket;

          if (backendPacket.type === "token") {
            sawTokenForCurrentAnswer = true;
          }

          if (
            backendPacket.type === "message" &&
            sawTokenForCurrentAnswer
          ) {
            // Token stream already provided this answer incrementally.
            // Skip duplicated full-message payload.
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
            getCategoryFor(backendPacket.type)?.id === GENERATED_FILE_CATEGORY_ID;
          // Reasoning resuming after the answer has already started (Gemini and
          // Claude can interleave "thinking" blocks between chunks of visible
          // text) is likewise exempt. It still lands in its own group via the
          // "reasoning" suffix, so treating it as a tool boundary here would
          // only fragment the in-progress answer into a new turn/message_start,
          // unmounting and re-typing the text that was already rendered.
          const isMidAnswerReasoningPkt =
            getCategoryFor(backendPacket.type)?.id === "reasoning" &&
            hasMessageStartForCurrentAnswer;
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
            const isNewCallStart =
              backendPacket.type === "custom_tool_start" &&
              !!callId &&
              !toolCallTurns.has(callId);
            if (!sawToolPackets) {
              turnIndex++; // display → tool: pre-tool text gets its own group
              sawTokenForCurrentAnswer = false;
              hasMessageStartForCurrentAnswer = false;
            } else if (
              (lastToolPacketType && shouldSplitCategories(lastToolPacketType, backendPacket.type)) ||
              isNewCallStart
            ) {
              turnIndex++;
              sawTokenForCurrentAnswer = false;
              hasMessageStartForCurrentAnswer = false;
            }
            sawToolPackets = true;
            lastToolPacketType = backendPacket.type;
            if (backendPacket.type === "custom_tool_start" && callId && !toolCallTurns.has(callId)) {
              toolCallTurns.set(callId, turnIndex);
            }
          } else if (sawToolPackets) {
            turnIndex++;
            sawToolPackets = false;
            lastToolPacketType = null;
            sawTokenForCurrentAnswer = false;
            hasMessageStartForCurrentAnswer = false;
          }

          if (backendPacket.type === "stop") {
            sawTokenForCurrentAnswer = false;
            hasMessageStartForCurrentAnswer = false;
          }

          if (backendPacket.type === "message_start") {
            const duration = (backendPacket as any).pre_answer_processing_seconds;
            yield {
              placement: { turn_index: turnIndex, sub_turn_index: null },
              obj: {
                type: "message_start",
                content: "",
                final_documents: null,
                pre_answer_processing_seconds: duration,
              },
            } as T;
            hasMessageStartForCurrentAnswer = true;
            continue;
          }

          if (backendPacket.type === "token" && !hasMessageStartForCurrentAnswer) {
            yield {
              placement: { turn_index: turnIndex, sub_turn_index: null },
              obj: {
                type: "message_start",
                content: "",
                final_documents: null,
              },
            } as T;
            hasMessageStartForCurrentAnswer = true;
          }

          if (backendPacket.type === "message" && !hasMessageStartForCurrentAnswer) {
            const duration = (backendPacket as any).content?.additional_kwargs?.processing_duration_seconds;
            yield {
              placement: { turn_index: turnIndex, sub_turn_index: null },
              obj: {
                type: "message_start",
                content: "",
                final_documents: null,
                pre_answer_processing_seconds: duration,
              },
            } as T;
            hasMessageStartForCurrentAnswer = true;
          }

          const mappedPacket = mapBackendToFrontend(backendPacket);

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

          yield mappedPacket as T;
        } catch (error) {
          console.error("Error parsing SSE data:", error);
        }
      }
    }
  } catch (error) {
    console.error('Stream error:', error);
    throw error;
  }
}
