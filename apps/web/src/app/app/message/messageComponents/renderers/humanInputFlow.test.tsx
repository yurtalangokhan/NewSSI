/**
 * End-to-end client pipeline for a paused FlowAgent run: the exact SSE line
 * AgentsRoute emits when a HumanInput node calls `interrupt()`, through
 * handleSSEStream and the packet processor, to the renderer that draws the
 * buttons.
 */
import { Packet, PacketType } from "@/app/app/services/streamingModels";
import { handleSSEStream } from "@/lib/search/streamingUtils";
import {
  createInitialState,
  processPackets,
} from "@/app/app/message/messageComponents/timeline/hooks/packetProcessor";
import { findRenderer } from "@/app/app/message/messageComponents/renderMessageComponent";
import { HumanInputRenderer } from "@/app/app/message/messageComponents/renderers/HumanInputRenderer";

// Byte-for-byte what AgentsRoute yields for a human_input interrupt.
const HUMAN_INPUT =
  'data: {"type":"human_input","node_id":"hi-1","prompt":"Bu gönderi taslağı için ne yapalım?","decisions":["yayinla","revize","iptal"]}\n';

function streamOf(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let next = 0;
  const reader = {
    read: async () =>
      next < chunks.length
        ? { done: false, value: encoder.encode(chunks[next++]!) }
        : { done: true, value: undefined },
    cancel: async () => {},
  };
  return { body: { getReader: () => reader } } as unknown as Response;
}

async function collect(chunks: string[]): Promise<Packet[]> {
  const packets: Packet[] = [];
  for await (const packet of handleSSEStream<any>(streamOf(chunks))) {
    packets.push(packet as Packet);
  }
  return packets;
}

describe("human input flow", () => {
  test("the interrupt line survives SSE parsing as a human_input packet", async () => {
    const packets = await collect([HUMAN_INPUT]);

    const request = packets.find((p) => p.obj.type === PacketType.HUMAN_INPUT);
    expect(request).toBeDefined();
    expect(request!.obj).toMatchObject({
      type: "human_input",
      node_id: "hi-1",
      prompt: "Bu gönderi taslağı için ne yapalım?",
      decisions: ["yayinla", "revize", "iptal"],
    });
  });

  test("the packet processor keeps it as a display group instead of dropping it", async () => {
    const packets = await collect([HUMAN_INPUT]);
    const state = processPackets(createInitialState(1), packets);

    const groups = state.potentialDisplayGroups.filter((g) =>
      g.packets.some((p) => p.obj.type === PacketType.HUMAN_INPUT)
    );
    expect(groups).toHaveLength(1);
  });

  test("the pause gets its own group, not the answer's", async () => {
    // A real run answers first and *then* parks. Sharing a group with the
    // answer would hand the mixed group to the text renderer and the buttons
    // would never render.
    const packets = await collect([
      'data: {"type":"token","content":"Taslak hazır."}\n',
      HUMAN_INPUT,
      "data: [DONE]\n",
    ]);
    const state = processPackets(createInitialState(1), packets);

    const groups = state.potentialDisplayGroups;
    const pause = groups.find((g) =>
      g.packets.some((p) => p.obj.type === PacketType.HUMAN_INPUT)
    );
    expect(pause).toBeDefined();
    expect(
      pause!.packets.some((p) => p.obj.type === PacketType.MESSAGE_DELTA)
    ).toBe(false);
    expect(findRenderer({ packets: pause!.packets })).toBe(HumanInputRenderer);

    // and the answer keeps its own bubble
    const answer = groups.find((g) =>
      g.packets.some((p) => p.obj.type === PacketType.MESSAGE_DELTA)
    );
    expect(answer).toBeDefined();
    expect(
      answer!.packets.some((p) => p.obj.type === PacketType.HUMAN_INPUT)
    ).toBe(false);
  });

  test("a reload replays it after the turn already stopped, and it still renders", async () => {
    // ChatController appends the pending interrupt to the last turn, i.e.
    // after that turn's `stop`. The group must still be built and dispatched,
    // or a reloaded pause shows no buttons.
    const packets = await collect([
      'data: {"type":"token","content":"Taslak hazır."}\n',
      "data: [DONE]\n",
      HUMAN_INPUT,
    ]);
    const state = processPackets(createInitialState(1), packets);

    const group = state.potentialDisplayGroups.find((g) =>
      g.packets.some((p) => p.obj.type === PacketType.HUMAN_INPUT)
    );
    expect(group).toBeDefined();
    expect(findRenderer({ packets: group!.packets })).toBe(HumanInputRenderer);
  });

  test("that group renders through HumanInputRenderer", async () => {
    const packets = await collect([HUMAN_INPUT]);
    const state = processPackets(createInitialState(1), packets);
    const group = state.potentialDisplayGroups.find((g) =>
      g.packets.some((p) => p.obj.type === PacketType.HUMAN_INPUT)
    )!;

    expect(findRenderer({ packets: group.packets })).toBe(HumanInputRenderer);
  });
});
