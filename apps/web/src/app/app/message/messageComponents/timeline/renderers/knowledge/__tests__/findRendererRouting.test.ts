import { findRenderer } from "@/app/app/message/messageComponents/renderMessageComponent";
import CustomToolRenderer from "@/app/app/message/messageComponents/renderers/CustomToolRenderer";
import KnowledgeRetrievalRenderer from "@/app/app/message/messageComponents/timeline/renderers/knowledge/KnowledgeRetrievalRenderer";
import { Packet, PacketType } from "@/lib/api/domains/chat/streaming-types";
import { knowledgePackets } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/__tests__/fixtures";

describe("findRenderer", () => {
  it("renders knowledge searches as evidence cards", () => {
    expect(findRenderer({ packets: knowledgePackets(null) })).toBe(
      KnowledgeRetrievalRenderer
    );
  });

  it("keeps other tools on the generic tool renderer", () => {
    const packets = [
      {
        placement: { turn_index: 0 },
        obj: {
          type: PacketType.CUSTOM_TOOL_START,
          tool_name: "calculator",
          args: {},
        },
      },
    ] as Packet[];

    expect(findRenderer({ packets })).toBe(CustomToolRenderer);
  });

  it("renders a flow component tool's evidence as a card whatever its name", () => {
    const [start, delta] = knowledgePackets(null, "DocumentSearch-a1b2");

    expect(findRenderer({ packets: [start!, delta!] })).toBe(
      KnowledgeRetrievalRenderer
    );
  });

  it("renders a flow component tool as a card before its result arrives", () => {
    const [start] = knowledgePackets(null, "DocumentSearch-a1b2");

    expect(findRenderer({ packets: [start!] })).toBe(
      KnowledgeRetrievalRenderer
    );
  });
});
