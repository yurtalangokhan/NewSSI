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
      // Full message - convert to message_start
      return {
        placement: defaultPlacement,
        obj: {
          type: "message_start",
          content: packet.content?.content || "",
          final_documents: null,
        },
      };
    
    case "token":
      // Token chunk - convert to message_delta
      return {
        placement: defaultPlacement,
        obj: {
          type: "message_delta",
          content: packet.content || "",
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
      console.log("aborting");
      reader?.cancel();
    });
  }
  while (true) {
    const rawChunk = await reader?.read();
    if (!rawChunk) {
      throw new Error("Unable to process chunk");
    }
    const { done, value } = rawChunk;
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.trim() === "") continue;

      // Handle SSE format: "data: {...}"
      let jsonLine = line;
      if (line.startsWith("data: ")) {
        jsonLine = line.slice(6); // Remove "data: " prefix
      }

      // Handle [DONE] marker
      if (jsonLine === "[DONE]") {
        yield {
          placement: { turn_index: 0, sub_turn_index: null },
          obj: { type: "stop", stop_reason: "finished" },
        } as T;
        continue;
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
}
