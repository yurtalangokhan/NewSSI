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
      obj: { type: "message_start", content: "" },
    });
    expect(packets[4]).toMatchObject({
      placement: { turn_index: 3 },
      obj: { type: "message_delta", content: "final" },
    });
  });

  it("renders full message packets when token streaming is unavailable", async () => {
    const response = createStreamingResponse([
      'data: {"type":"message","content":{"type":"ai","content":"full answer"}}\n',
      'data: [DONE]\n',
    ]);

    const packets = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    expect(packets).toHaveLength(3);
    expect(packets[0]).toMatchObject({
      obj: { type: "message_start", content: "" },
    });
    expect(packets[1]).toMatchObject({
      obj: { type: "message_delta", content: "full answer" },
    });
    expect(packets[2]).toMatchObject({
      obj: { type: "stop" },
    });
  });

  it("surfaces backend error packets as streaming errors", async () => {
    const response = createStreamingResponse([
      'data: {"type":"error","content":"LLM failed"}\n',
      'data: [DONE]\n',
    ]);

    const packets = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    expect(packets[0]).toMatchObject({
      error: "LLM failed",
      stack_trace: "",
    });
  });
  it("keeps a document generation and its file in one timeline turn", async () => {
    // The skeleton must be replaced in place by the finished file card, even
    // when the model streams answer text between the two.
    const response = createStreamingResponse([
      'data: {"type":"token","content":"Hazırlıyorum"}\n',
      'data: {"type":"document_generation_start","tool_name":"create_document","filename":null,"format":null,"phase":"writing"}\n',
      'data: {"type":"document_generation_progress","tool_name":"create_document","filename":"rapor","format":"pdf","phase":"writing","chars":600}\n',
      'data: {"type":"token","content":"biraz sürebilir"}\n',
      'data: {"type":"generated_file","file_id":"abc123","filename":"rapor.pdf","mime_type":"application/pdf","size_bytes":42,"download_url":"/api/chat/file/abc123?download=1"}\n',
      'data: {"type":"document_generation_end","tool_name":"create_document","filename":"rapor.pdf","format":"pdf","status":"success","error":null}\n',
      'data: [DONE]\n',
    ]);

    const packets: any[] = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    const turnOf = (type: string) =>
      packets.find((p) => p.obj?.type === type)?.placement.turn_index;

    const documentTurn = turnOf("document_generation_start");
    expect(documentTurn).toBeDefined();
    expect(turnOf("document_generation_progress")).toBe(documentTurn);
    expect(turnOf("generated_file")).toBe(documentTurn);
    expect(turnOf("document_generation_end")).toBe(documentTurn);

    // The generation shares the answer's turn rather than splitting it: a model
    // that starts its tool call mid-sentence would otherwise cut the reply in
    // two around the file card. The packet processor still gives the document
    // its own group via the "genfile" group suffix.
    expect(documentTurn).toBe(packets[0]!.placement.turn_index);
    const answerTurns = packets
      .filter((p) => p.obj?.type === "message_delta")
      .map((p) => p.placement.turn_index);
    expect(new Set(answerTurns).size).toBe(1);
  });

  it("does not open a new turn for a file packet with no generation around it", async () => {
    const response = createStreamingResponse([
      'data: {"type":"generated_file","file_id":"abc123","filename":"rapor.pdf","mime_type":"application/pdf","size_bytes":42,"download_url":"/api/chat/file/abc123?download=1"}\n',
      'data: [DONE]\n',
    ]);

    const packets = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    expect(packets[0]).toMatchObject({
      placement: { turn_index: 0 },
      obj: { type: "generated_file" },
    });
  });
  it("keeps a retry after a rejected tool call in the same turn", async () => {
    // The agent is told to fix its arguments and call the tool again; the
    // successful retry must replace the failure notice, not stack under it.
    const response = createStreamingResponse([
      'data: {"type":"document_generation_start","tool_name":"create_document","filename":null,"format":null,"phase":"writing"}\n',
      'data: {"type":"document_generation_end","tool_name":"create_document","filename":null,"format":"pdf","status":"error","error":"Error: missing content"}\n',
      'data: {"type":"document_generation_start","tool_name":"create_document","filename":"rapor","format":"pdf","phase":"writing"}\n',
      'data: {"type":"generated_file","file_id":"abc123","filename":"rapor.pdf","mime_type":"application/pdf","size_bytes":42,"download_url":"/api/chat/file/abc123?download=1"}\n',
      'data: {"type":"document_generation_end","tool_name":"create_document","filename":"rapor.pdf","format":"pdf","status":"success","error":null}\n',
      'data: [DONE]\n',
    ]);

    const packets: any[] = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    const documentTurns = new Set(
      packets
        .filter((p) => String(p.obj?.type).startsWith("document_generation"))
        .concat(packets.filter((p) => p.obj?.type === "generated_file"))
        .map((p) => p.placement.turn_index)
    );
    expect(documentTurns.size).toBe(1);
  });

  it("handles document generation arriving during reasoning without altering tool turn pacing", async () => {
    const response = createStreamingResponse([
      'data: {"type":"reasoning_start"}\n',
      'data: {"type":"reasoning_delta","reasoning":"Thinking about document..."}\n',
      'data: {"type":"document_generation_start","tool_name":"create_document","filename":null,"format":null,"phase":"writing"}\n',
      'data: {"type":"document_generation_progress","tool_name":"create_document","filename":"report","format":"pdf","phase":"writing","chars":200}\n',
      'data: {"type":"reasoning_delta","reasoning":"Still thinking..."}\n',
      'data: {"type":"generated_file","file_id":"abc123","filename":"report.pdf","mime_type":"application/pdf","size_bytes":42,"download_url":"/api/chat/file/abc123?download=1"}\n',
      'data: {"type":"document_generation_end","tool_name":"create_document","filename":"report.pdf","format":"pdf","status":"success","error":null}\n',
      'data: [DONE]\n',
    ]);

    const packets: any[] = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    const reasoningPackets = packets.filter((p) =>
      String(p.obj?.type).startsWith("reasoning")
    );
    const reasoningTurns = new Set(
      reasoningPackets.map((p) => p.placement.turn_index)
    );
    // Reasoning should remain in a single turn index, not split by document generation packets
    expect(reasoningTurns.size).toBe(1);
  });

  it("does not fragment the answer when reasoning resumes mid-answer", async () => {
    // Gemini/Claude can interleave "thinking" blocks between chunks of
    // visible text (think a bit -> write a bit -> think a bit -> write a
    // bit). Treating that resumed reasoning as a tool boundary would bump
    // turn_index, force a new message_start, and unmount/re-type the answer
    // that already streamed in.
    const response = createStreamingResponse([
      'data: {"type":"reasoning_start"}\n',
      'data: {"type":"reasoning_delta","reasoning":"planning"}\n',
      'data: {"type":"token","content":"Here is "}\n',
      'data: {"type":"reasoning_start"}\n',
      'data: {"type":"reasoning_delta","reasoning":"more thinking"}\n',
      'data: {"type":"token","content":"the rest."}\n',
      'data: [DONE]\n',
    ]);

    const packets: any[] = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    const answerTurns = packets
      .filter((p) => p.obj?.type === "message_delta")
      .map((p) => p.placement.turn_index);
    // Both token chunks belong to the same answer turn.
    expect(new Set(answerTurns).size).toBe(1);

    // Only one message_start was ever synthesized for this answer — the
    // resumed reasoning must not have forced a second one.
    const messageStarts = packets.filter((p) => p.obj?.type === "message_start");
    expect(messageStarts).toHaveLength(1);
  });

  it("gives each parallel tool call its own turn, keyed by call_id", async () => {
    // A deep-research turn fires several web_search calls at once: all their
    // custom_tool_start packets arrive before any result comes back. Without
    // call_id-based splitting, every call lands in one turn and only the
    // last call's result is attributed to it.
    const response = createStreamingResponse([
      'data: {"type":"custom_tool_start","tool_name":"web_search","args":{"query":"a"},"call_id":"call-a"}\n',
      'data: {"type":"custom_tool_start","tool_name":"web_search","args":{"query":"b"},"call_id":"call-b"}\n',
      'data: {"type":"custom_tool_delta","tool_name":"web_search","response_type":"tool_result","data":"result a","call_id":"call-a"}\n',
      'data: {"type":"custom_tool_delta","tool_name":"web_search","response_type":"tool_result","data":"result b","call_id":"call-b"}\n',
      'data: [DONE]\n',
    ]);

    const packets: any[] = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    const starts = packets.filter((p) => p.obj?.type === "custom_tool_start");
    const deltas = packets.filter((p) => p.obj?.type === "custom_tool_delta");
    expect(starts).toHaveLength(2);
    expect(deltas).toHaveLength(2);

    const turnOf = (call_id: string, type: string) =>
      packets.find((p) => p.obj?.type === type && p.obj?.call_id === call_id)
        ?.placement.turn_index;

    // Each call's start and its own delta share a turn, but the two calls
    // don't share a turn with each other.
    expect(turnOf("call-a", "custom_tool_start")).toBe(
      turnOf("call-a", "custom_tool_delta")
    );
    expect(turnOf("call-b", "custom_tool_start")).toBe(
      turnOf("call-b", "custom_tool_delta")
    );
    expect(turnOf("call-a", "custom_tool_start")).not.toBe(
      turnOf("call-b", "custom_tool_start")
    );
  });
  it("ignores SSE keep-alive comments", async () => {
    // The backend sends ": keep-alive" comments during long silent
    // generations so proxies don't drop the connection. They carry no
    // packet and must not surface as parse errors or stray packets.
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    const response = createStreamingResponse([
      ': keep-alive\n',
      'data: {"type":"token","content":"Hi"}\n',
      ': keep-alive\n',
      'data: [DONE]\n',
    ]);

    const packets: any[] = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    expect(packets.map((p) => p.obj?.type)).toEqual([
      "message_start",
      "message_delta",
      "stop",
    ]);
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });

  it("passes the real message-id packet through unwrapped, not nested under obj", async () => {
    // This packet has no `type` field, so the generic default case would
    // otherwise wrap it as `{ obj: packet }` — but the consumer
    // (useChatController.ts) reads `packet.user_message_id` /
    // `packet.reserved_assistant_message_id` directly on the top-level
    // packet, matching the MessageResponseIDInfo shape. Wrapped, those
    // fields are silently unreadable and the message never gets its real
    // id — retry and the alternate-response switcher then stay broken
    // until the page is reloaded.
    const response = createStreamingResponse([
      'data: {"type":"token","content":"Hi"}\n',
      'data: {"user_message_id": 1, "reserved_assistant_message_id": 2}\n',
      'data: [DONE]\n',
    ]);

    const packets: any[] = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    const idPacket = packets.find(
      (p) => p.reserved_assistant_message_id !== undefined
    );
    expect(idPacket).toEqual({
      user_message_id: 1,
      reserved_assistant_message_id: 2,
    });
  });
});

