import { PacketType } from "@/app/app/services/lib";

// Backend packet types from our agent-service
interface BackendPacket {
  type: string;
  content?: any;
}

// Map backend packets to frontend PacketType
function mapBackendToFrontend(packet: BackendPacket): { placement: any; obj: any } {
  const defaultPlacement = { turn_index: 0, sub_turn_index: null };
  
  switch (packet.type) {
    case "message":
      // Full message - could be ai message or tool message
      // Extract content from nested structure
      let messageContent = "";
      const content = packet.content;
      if (typeof content === "string") {
        messageContent = content;
      } else if (typeof content === "object" && content !== null) {
        // Handle LangChain message format: {type: "ai", content: "...", tool_calls: [...]}
        if (content.content !== undefined) {
          if (typeof content.content === "string") {
            messageContent = content.content;
          } else if (Array.isArray(content.content)) {
            // Handle array format [{type: "text", text: "..."}]
            for (const item of content.content) {
              if (typeof item === "object" && item?.type === "text") {
                messageContent = item.text || "";
                break;
              }
            }
          }
        }
      }
      
      return {
        placement: defaultPlacement,
        obj: {
          type: "message_start",
          content: messageContent,
          final_documents: null,
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
        obj: {
          type: "error",
          message: packet.content || "Unknown error",
        },
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
    
    default:
      // Unknown packet type - return as-is wrapped
      return {
        placement: defaultPlacement,
        obj: packet,
      };
  }
}

// Packet types that represent tool/step lifecycle events (shown in timeline)
// Adding a new type here causes the stream parser to advance turnIndex at
// that boundary, placing subsequent packets in a fresh timeline group.
const TOOL_PACKET_TYPES = new Set([
  "custom_tool_start", "custom_tool_delta",
  "custom_step_start",
  "search_tool_start", "search_tool_queries_delta", "search_tool_documents_delta",
]);

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
  // If tokens were already streamed for the current answer, skip the later
  // full "message" packet from backend to avoid duplicate text rendering.
  let sawTokenForCurrentAnswer = false;
  
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
          const isToolPkt = TOOL_PACKET_TYPES.has(backendPacket.type);
          if (isToolPkt) {
            if (!sawToolPackets) {
              turnIndex++; // display → tool: pre-tool text gets its own group
              sawTokenForCurrentAnswer = false;
            }
            sawToolPackets = true;
          } else if (sawToolPackets) {
            turnIndex++;
            sawToolPackets = false;
            sawTokenForCurrentAnswer = false;
          }

          if (backendPacket.type === "stop") {
            sawTokenForCurrentAnswer = false;
          }

          const mappedPacket = mapBackendToFrontend(backendPacket);
          mappedPacket.placement.turn_index = turnIndex;
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
