import { handleSSEStream } from "./streamingUtils";

function createStreamingResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });

  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("handleSSEStream", () => {
  it("emits a synthetic message_start before the first token packet", async () => {
    const response = createStreamingResponse([
      'data: {"type":"token","content":"Hello"}\n',
      'data: [DONE]\n',
    ]);

    const packets = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    expect(packets).toHaveLength(3);
    expect(packets[0]).toMatchObject({
      obj: {
        type: "message_start",
        content: "",
        final_documents: null,
      },
    });
    expect(packets[1]).toMatchObject({
      obj: {
        type: "message_delta",
        content: "Hello",
      },
    });
    expect(packets[2]).toMatchObject({
      obj: {
        type: "stop",
      },
    });
  });
});