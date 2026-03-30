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
            placement: { turn_index: 0, sub_turn_index: null },
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
          const mappedPacket = mapBackendToFrontend(backendPacket);
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
