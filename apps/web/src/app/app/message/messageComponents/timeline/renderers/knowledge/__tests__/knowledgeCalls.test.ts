import { Packet, PacketType } from "@/lib/api/domains/chat/streaming-types";
import {
  constructKnowledgeCalls,
  isGraphCall,
  isKnowledgePacket,
} from "@/app/app/message/messageComponents/timeline/renderers/knowledge/knowledgeCalls";

const evidence = {
  schema_version: 1,
  kind: "document",
  tool: "database_search",
  query: "izin devri",
  chunks: [{ ref: 1, content: "Kullanılmayan izin devredilir." }],
};

function packet(obj: Record<string, unknown>): Packet {
  return { placement: { turn_index: 0 }, obj } as unknown as Packet;
}

const start = (callId: string, toolName = "database_search") =>
  packet({
    type: PacketType.CUSTOM_TOOL_START,
    tool_name: toolName,
    args: { query: "izin devri" },
    call_id: callId,
  });

const knowledgeDelta = (callId: string, data: unknown = evidence) =>
  packet({
    type: PacketType.CUSTOM_TOOL_DELTA,
    tool_name: "database_search",
    response_type: "knowledge_retrieval",
    evidence_id: "e-1",
    data,
    call_id: callId,
  });

describe("isKnowledgePacket", () => {
  it("recognises knowledge deltas and knowledge tool starts", () => {
    expect(isKnowledgePacket(knowledgeDelta("c1"))).toBe(true);
    expect(isKnowledgePacket(start("c1"))).toBe(true);
    expect(isKnowledgePacket(start("c1", "graph_search"))).toBe(true);
  });

  it("recognises a flow component tool from its start alone", () => {
    expect(isKnowledgePacket(start("c1", "DocumentSearch-a1b2"))).toBe(true);
    expect(isKnowledgePacket(start("c1", "GraphSearch-a1b2"))).toBe(true);
  });

  it("does not mistake other flow component tools for searches", () => {
    expect(isKnowledgePacket(start("c1", "Calculator-a1b2"))).toBe(false);
    expect(isKnowledgePacket(start("c1", "DocumentSearchX-a1b2"))).toBe(false);
    expect(isKnowledgePacket(start("c1", "DocumentSearch"))).toBe(false);
  });

  it("leaves every other tool to its own renderer", () => {
    expect(isKnowledgePacket(start("c1", "calculator"))).toBe(false);
    expect(
      isKnowledgePacket(
        packet({
          type: PacketType.CUSTOM_TOOL_DELTA,
          tool_name: "calculator",
          response_type: "tool_result",
          data: "4",
        })
      )
    ).toBe(false);
  });
});

describe("constructKnowledgeCalls", () => {
  it("pairs each call's start with its evidence", () => {
    const calls = constructKnowledgeCalls([start("c1"), knowledgeDelta("c1")]);

    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({
      callId: "c1",
      toolName: "database_search",
      query: "izin devri",
      status: "done",
      fallbackText: null,
    });
    expect(calls[0]?.evidence?.chunks[0]?.content).toBe(
      "Kullanılmayan izin devredilir."
    );
  });

  it("keeps a running call without a result", () => {
    const [call] = constructKnowledgeCalls([start("c1")]);

    expect(call?.status).toBe("running");
    expect(call?.evidence).toBeNull();
  });

  it("marks evidence that could not be loaded as unavailable", () => {
    const [call] = constructKnowledgeCalls([
      start("c1"),
      knowledgeDelta("c1", null),
    ]);

    expect(call?.status).toBe("unavailable");
  });

  it("falls back to the plain text of a result without evidence", () => {
    const [call] = constructKnowledgeCalls([
      start("c1"),
      packet({
        type: PacketType.CUSTOM_TOOL_DELTA,
        tool_name: "database_search",
        response_type: "tool_result",
        data: '{"success": false, "error": "Bilgi erişimi başarısız oldu."}',
        call_id: "c1",
      }),
    ]);

    expect(call?.status).toBe("done");
    expect(call?.fallbackText).toContain("Bilgi erişimi başarısız oldu.");
  });

  it("matches results to calls by id when parallel calls interleave", () => {
    const calls = constructKnowledgeCalls([
      start("a"),
      start("b", "graph_search"),
      knowledgeDelta("b", { ...evidence, kind: "graph", tool: "graph_search" }),
      knowledgeDelta("a"),
    ]);

    expect(calls.map((call) => [call.callId, call.evidence?.kind])).toEqual([
      ["a", "document"],
      ["b", "graph"],
    ]);
  });

  it("keeps a result whose start never arrived", () => {
    const [call] = constructKnowledgeCalls([knowledgeDelta("orphan")]);

    expect(call?.callId).toBe("orphan");
    expect(call?.query).toBe("izin devri");
  });
});

describe("isGraphCall", () => {
  it("knows a running flow component graph search by its name", () => {
    const [graph] = constructKnowledgeCalls([start("c1", "GraphSearch-a1b2")]);
    const [documents] = constructKnowledgeCalls([
      start("c2", "DocumentSearch-a1b2"),
    ]);

    expect(isGraphCall(graph!)).toBe(true);
    expect(isGraphCall(documents!)).toBe(false);
  });
});
