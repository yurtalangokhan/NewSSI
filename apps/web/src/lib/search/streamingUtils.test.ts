import { handleSSEStream } from "./streamingUtils";
import type { RunMetaPacket } from "@/lib/api/domains/chat/run-types";

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
      "data: [DONE]\n",
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
      "data: [DONE]\n",
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
      "data: [DONE]\n",
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
      "data: [DONE]\n",
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
      "data: [DONE]\n",
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
      "data: [DONE]\n",
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
      "data: [DONE]\n",
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
      "data: [DONE]\n",
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
      "data: [DONE]\n",
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
      "data: [DONE]\n",
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
    const messageStarts = packets.filter(
      (p) => p.obj?.type === "message_start"
    );
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
      "data: [DONE]\n",
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
      ": keep-alive\n",
      'data: {"type":"token","content":"Hi"}\n',
      ": keep-alive\n",
      "data: [DONE]\n",
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
      "data: [DONE]\n",
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
  it("gives each parallel open_url / fetch_webpage call its own turn", async () => {
    const response = createStreamingResponse([
      'data: {"type":"open_url_start","call_id":"fetch-1"}\n',
      'data: {"type":"open_url_urls","urls":["https://site1.com"],"call_id":"fetch-1"}\n',
      'data: {"type":"open_url_start","call_id":"fetch-2"}\n',
      'data: {"type":"open_url_urls","urls":["https://site2.com"],"call_id":"fetch-2"}\n',
      'data: {"type":"open_url_documents","documents":[{"document_id":"https://site1.com","semantic_identifier":"Site 1"}],"call_id":"fetch-1"}\n',
      'data: {"type":"open_url_documents","documents":[{"document_id":"https://site2.com","semantic_identifier":"Site 2"}],"call_id":"fetch-2"}\n',
      "data: [DONE]\n",
    ]);

    const packets: any[] = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    const turnOf = (call_id: string, type: string) =>
      packets.find((p) => p.obj?.type === type && p.obj?.call_id === call_id)
        ?.placement.turn_index;

    expect(turnOf("fetch-1", "open_url_start")).toBe(
      turnOf("fetch-1", "open_url_documents")
    );
    expect(turnOf("fetch-2", "open_url_start")).toBe(
      turnOf("fetch-2", "open_url_documents")
    );
    expect(turnOf("fetch-1", "open_url_start")).not.toBe(
      turnOf("fetch-2", "open_url_start")
    );
  });
  it("splits interleaved search and fetch calls into distinct timeline turns", async () => {
    const response = createStreamingResponse([
      'data: {"type":"search_tool_start","is_internet_search":true,"call_id":"search-1"}\n',
      'data: {"type":"search_tool_queries_delta","queries":["query 1"],"call_id":"search-1"}\n',
      'data: {"type":"open_url_start","call_id":"fetch-1"}\n',
      'data: {"type":"open_url_urls","urls":["https://site1.com"],"call_id":"fetch-1"}\n',
      'data: {"type":"search_tool_start","is_internet_search":true,"call_id":"search-2"}\n',
      'data: {"type":"search_tool_queries_delta","queries":["query 2"],"call_id":"search-2"}\n',
      'data: {"type":"open_url_documents","documents":[{"document_id":"https://site1.com","semantic_identifier":"Site 1"}],"call_id":"fetch-1"}\n',
      'data: {"type":"search_tool_documents_delta","documents":[{"document_id":"https://res1.com","semantic_identifier":"Res 1"}],"call_id":"search-1"}\n',
      'data: {"type":"search_tool_documents_delta","documents":[{"document_id":"https://res2.com","semantic_identifier":"Res 2"}],"call_id":"search-2"}\n',
      "data: [DONE]\n",
    ]);

    const packets: any[] = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    const turnOf = (call_id: string, type: string) =>
      packets.find((p) => p.obj?.type === type && p.obj?.call_id === call_id)
        ?.placement.turn_index;

    const s1Turn = turnOf("search-1", "search_tool_start");
    const f1Turn = turnOf("fetch-1", "open_url_start");
    const s2Turn = turnOf("search-2", "search_tool_start");

    expect(s1Turn).toBeDefined();
    expect(f1Turn).toBeDefined();
    expect(s2Turn).toBeDefined();

    expect(s1Turn).not.toBe(f1Turn);
    expect(f1Turn).not.toBe(s2Turn);
    expect(s1Turn).not.toBe(s2Turn);

    expect(turnOf("fetch-1", "open_url_documents")).toBe(f1Turn);
    expect(turnOf("search-1", "search_tool_documents_delta")).toBe(s1Turn);
    expect(turnOf("search-2", "search_tool_documents_delta")).toBe(s2Turn);
  });

  it("passes graph_stage_start/graph_stage_end through with their stage_name", async () => {
    const response = createStreamingResponse([
      'data: {"type":"graph_stage_start","stage_name":"ChatInput-1"}\n',
      'data: {"type":"graph_stage_end","stage_name":"ChatInput-1"}\n',
      "data: [DONE]\n",
    ]);

    const packets = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    const stageObjs = packets
      .map((p: any) => p.obj)
      .filter((o: any) => o?.type?.startsWith("graph_stage_"));

    expect(stageObjs).toEqual([
      { type: "graph_stage_start", stage_name: "ChatInput-1" },
      { type: "graph_stage_end", stage_name: "ChatInput-1" },
    ]);
  });
  it("carries the backend's is_loop_body flag into placement (B18)", async () => {
    const response = createStreamingResponse([
      'data: {"type":"flow_stage_start","stage_key":"A#1","node_id":"A","label":"Analiz","stage_order":1,"iteration":1,"is_final_stage":false,"is_loop_body":true}\n',
      "data: [DONE]\n",
    ]);

    const packets: any[] = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    const start = packets.find((p) => p.obj?.type === "flow_stage_start");
    expect(start.placement).toMatchObject({
      stage_key: "A#1",
      is_loop_body: true,
    });
  });

  it("carries FlowAgent stage identity into placement for flow_stage_* and stage-scoped packets", async () => {
    const response = createStreamingResponse([
      'data: {"type":"flow_stage_start","stage_key":"A#1","node_id":"A","label":"Analiz","stage_order":1,"iteration":1,"is_final_stage":false}\n',
      'data: {"type":"reasoning_delta","reasoning":"hmm","stage_key":"A#1","stage_order":1,"iteration":1}\n',
      'data: {"type":"flow_stage_output_delta","stage_key":"A#1","stage_order":1,"iteration":1,"content":"ara"}\n',
      'data: {"type":"flow_stage_end","stage_key":"A#1","status":"done","duration_ms":1200}\n',
      "data: [DONE]\n",
    ]);

    const packets: any[] = [];
    for await (const packet of handleSSEStream<any>(response)) {
      packets.push(packet);
    }

    const start = packets.find((p) => p.obj?.type === "flow_stage_start");
    expect(start.placement).toMatchObject({
      stage_key: "A#1",
      stage_order: 1,
      iteration: 1,
      is_final_stage: false,
    });
    expect(start.obj).toMatchObject({ label: "Analiz", node_id: "A" });

    const reasoning = packets.find((p) => p.obj?.type === "reasoning_delta");
    expect(reasoning.placement).toMatchObject({
      stage_key: "A#1",
      stage_order: 1,
      iteration: 1,
    });

    const output = packets.find(
      (p) => p.obj?.type === "flow_stage_output_delta"
    );
    expect(output.placement.stage_key).toBe("A#1");
    expect(output.obj.content).toBe("ara");

    const end = packets.find((p) => p.obj?.type === "flow_stage_end");
    expect(end.placement.stage_key).toBe("A#1");
    expect(end.obj.duration_ms).toBe(1200);
  });
});

describe("handleSSEStream resumable options", () => {
  const frame = (id: number, data: string) => `id: ${id}\ndata: ${data}\n\n`;

  async function collect<T>(gen: AsyncGenerator<T>): Promise<T[]> {
    const out: T[] = [];
    for await (const item of gen) out.push(item);
    return out;
  }

  const body =
    frame(1, '{"type":"run_started","run_id":"r1","thread_id":"t1"}') +
    frame(
      2,
      '{"type":"custom_tool_start","tool_name":"web_search","args":{},"call_id":"c1","timestamp":1}'
    ) +
    frame(
      3,
      '{"type":"custom_tool_delta","tool_name":"web_search","response_type":"tool_result","data":"ok","call_id":"c1","timestamp":2}'
    ) +
    frame(4, '{"type":"token","content":"Answer"}') +
    frame(5, '{"type":"run_end","status":"completed","error_code":null}') +
    frame(6, "[DONE]");

  it("reports event ids and hides run meta packets", async () => {
    const ids: number[] = [];
    const meta: RunMetaPacket[] = [];
    const packets = await collect(
      handleSSEStream(new Response(body), undefined, {
        onEventId: (seq: number) => ids.push(seq),
        onRunMeta: (m: RunMetaPacket) => meta.push(m),
      })
    );
    expect(ids).toEqual([1, 2, 3, 4, 5, 6]);
    expect(meta.map((m) => m.type)).toEqual(["run_started", "run_end"]);
    expect(JSON.stringify(packets)).not.toContain("run_started");
    expect(JSON.stringify(packets)).not.toContain("run_end");
  });

  it("suppresses already delivered events but keeps turn bookkeeping", async () => {
    const tagged: Array<{ seq: number; packet: unknown }> = [];
    let pending: unknown[] = [];
    for await (const packet of handleSSEStream(new Response(body), undefined, {
      onEventId: (seq: number) => {
        pending.forEach((p) => tagged.push({ seq, packet: p }));
        pending = [];
      },
    })) {
      pending.push(packet);
    }
    const resumed = await collect(
      handleSSEStream(new Response(body), undefined, { suppressThroughSeq: 3 })
    );
    expect(resumed).toEqual(
      tagged.filter((t) => t.seq > 3).map((t) => t.packet)
    );
    expect(resumed.length).toBeGreaterThan(0);
  });

  it("reports resync as run meta", async () => {
    const meta: RunMetaPacket[] = [];
    await collect(
      handleSSEStream(
        new Response('data: {"type":"resync","first_available_seq":9}\n\n'),
        undefined,
        {
          onRunMeta: (m: RunMetaPacket) => meta.push(m),
        }
      )
    );
    expect(meta).toEqual([{ type: "resync", first_available_seq: 9 }]);
  });

  it("treats a stream without ids exactly as before", async () => {
    const legacy = 'data: {"type":"token","content":"x"}\n\ndata: [DONE]\n\n';
    const withIds =
      frame(1, '{"type":"token","content":"x"}') + frame(2, "[DONE]");
    expect(await collect(handleSSEStream(new Response(legacy)))).toEqual(
      await collect(handleSSEStream(new Response(withIds)))
    );
  });
});

describe("handleSSEStream event ids at a broken stream", () => {
  async function collect<T>(gen: AsyncGenerator<T>): Promise<T[]> {
    const out: T[] = [];
    for await (const item of gen) out.push(item);
    return out;
  }
  function chunkedResponse(chunks: string[], error?: Error): Response {
    const encoder = new TextEncoder();
    let index = 0;
    const body = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (index < chunks.length) {
          controller.enqueue(encoder.encode(chunks[index++]));
        } else if (error) {
          controller.error(error);
        } else {
          controller.close();
        }
      },
    });
    return new Response(body);
  }
  const token = (id: number, content: string) =>
    `id: ${id}\ndata: {"type":"token","content":"${content}"}\n\n`;

  it("never reports an id whose data line did not arrive", async () => {
    const ids: number[] = [];
    await collect(
      handleSSEStream(
        chunkedResponse([token(1, "A"), token(2, "B"), "id: 3\n"]),
        undefined,
        { onEventId: (seq) => ids.push(seq) }
      )
    );
    expect(ids).toEqual([1, 2]);
  });

  it("reports the id of a delivered event even when the stream then fails", async () => {
    const ids: number[] = [];
    await expect(
      collect(
        handleSSEStream(
          chunkedResponse(
            [token(1, "A"), 'id: 2\ndata: {"type":"token","content":"B"}\n'],
            new Error("network")
          ),
          undefined,
          { onEventId: (seq) => ids.push(seq) }
        )
      )
    ).rejects.toThrow("network");
    expect(ids).toEqual([1, 2]);
  });
});
