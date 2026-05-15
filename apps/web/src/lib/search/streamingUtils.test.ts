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

  it("places long-term memory recall into its own timeline turn", async () => {
    const response = createStreamingResponse([
      'data: {"type":"token","content":"Hello"}\n',
      'data: {"type":"long_term_memory_recall","fact_count":1,"memories":["User likes tea"]}\n',
      'data: {"type":"token","content":" again"}\n',
      'data: [DONE]\n',
    ]);

    const packets = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    expect(packets[0]).toMatchObject({
      placement: { turn_index: 0 },
      obj: { type: "message_start" },
    });
    expect(packets[1]).toMatchObject({
      placement: { turn_index: 0 },
      obj: { type: "message_delta", content: "Hello" },
    });
    expect(packets[2]).toMatchObject({
      placement: { turn_index: 1 },
      obj: { type: "long_term_memory_recall", fact_count: 1 },
    });
    expect(packets[3]).toMatchObject({
      placement: { turn_index: 2 },
      obj: { type: "message_start" },
    });
    expect(packets[4]).toMatchObject({
      placement: { turn_index: 2 },
      obj: { type: "message_delta", content: " again" },
    });
  });

  it("splits long-term memory and reasoning into separate tool turns", async () => {
    const response = createStreamingResponse([
      'data: {"type":"long_term_memory_recall","fact_count":2,"memories":["A","B"]}\n',
      'data: {"type":"reasoning_start"}\n',
      'data: {"type":"reasoning_delta","reasoning":"plan"}\n',
      'data: {"type":"message","content":{"type":"ai","content":"final"}}\n',
      'data: [DONE]\n',
    ]);

    const packets = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    expect(packets[0]).toMatchObject({
      placement: { turn_index: 1 },
      obj: { type: "long_term_memory_recall", fact_count: 2 },
    });
    expect(packets[1]).toMatchObject({
      placement: { turn_index: 2 },
      obj: { type: "reasoning_start" },
    });
    expect(packets[2]).toMatchObject({
      placement: { turn_index: 2 },
      obj: { type: "reasoning_delta", reasoning: "plan" },
    });
    expect(packets[3]).toMatchObject({
      placement: { turn_index: 3 },
      obj: { type: "message_start", content: "final" },
    });
  });
});