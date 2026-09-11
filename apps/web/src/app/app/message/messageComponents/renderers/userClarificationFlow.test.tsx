/**
 * End-to-end client pipeline for an `ask_user` pause: the exact SSE lines
 * AgentStreamService emits when the tool calls `interrupt()`, through
 * handleSSEStream and the packet processor, to the renderer that draws the
 * card.
 *
 * This is the test that matters for the live path. A reload rebuilds the card
 * from the checkpoint and takes a different route through the client, so a
 * renderer unit test passing proves nothing about what the user sees while
 * the run is actually paused.
 */
import { renderHook } from "@testing-library/react";
import { Packet, PacketType } from "@/app/app/services/streamingModels";
import { handleSSEStream } from "@/lib/search/streamingUtils";
import {
  createInitialState,
  processPackets,
} from "@/app/app/message/messageComponents/timeline/hooks/packetProcessor";
import { findRenderer } from "@/app/app/message/messageComponents/renderMessageComponent";
import { UserClarificationRenderer } from "@/app/app/message/messageComponents/renderers/UserClarificationRenderer";
import {
  isFinalAnswerComing,
  isDisplayPacket,
} from "@/app/app/services/packetUtils";
import { usePacketProcessor } from "@/app/app/message/messageComponents/timeline/hooks/usePacketProcessor";

// Byte-for-byte what AgentStreamService yields for an ask_user interrupt.
const CLARIFICATION =
  'data: {"type":"user_clarification","v":1,"request_id":"int-42","questions":[{"question":"Raporu kim okuyacak?","header":"Hedef kitle","options":[{"label":"Yönetim","description":"Özet"},{"label":"Teknik ekip","description":"Detay"}],"multiSelect":false}],"agent_path":[]}\n';
const STOP = 'data: {"type":"stop","stop_reason":"finished"}\n';
// A real turn reasons first: the model decides it cannot tell what was meant.
const REASONING_START = 'data: {"type":"reasoning_start"}\n';
const REASONING_DELTA =
  'data: {"type":"reasoning_delta","reasoning":"Hangi veriyi istiyor?"}\n';

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

function cardGroup(packets: Packet[]) {
  const state = processPackets(createInitialState(1), packets);
  return state.potentialDisplayGroups.find((g) =>
    g.packets.some((p) => p.obj.type === PacketType.USER_CLARIFICATION)
  );
}

describe("ask_user pause, live", () => {
  test("the interrupt line survives SSE parsing as a clarification packet", async () => {
    const packets = await collect([CLARIFICATION]);

    const card = packets.find(
      (p) => p.obj.type === PacketType.USER_CLARIFICATION
    );
    expect(card).toBeDefined();
    expect(card!.obj).toMatchObject({
      type: "user_clarification",
      v: 1,
      request_id: "int-42",
    });
  });

  test("a paused turn counts as display content, not as withheld text", () => {
    // Both gates matter: the card is the whole visible output of the turn, so
    // if either says "nothing to show" the run looks silently stuck.
    const card = {
      obj: { type: PacketType.USER_CLARIFICATION },
    } as unknown as Packet;
    expect(isDisplayPacket(card)).toBe(true);
    expect(isFinalAnswerComing([card])).toBe(true);
  });

  test("the packet processor keeps it as a display group", async () => {
    expect(cardGroup(await collect([CLARIFICATION]))).toBeDefined();
  });

  test("the card group reaches its own renderer", async () => {
    const group = cardGroup(await collect([CLARIFICATION]));

    expect(findRenderer({ packets: group!.packets })).toBe(
      UserClarificationRenderer
    );
  });

  test("reasoning before the question does not swallow the card", async () => {
    // The real shape: the model thinks, decides to ask, and parks. If the
    // card shares the reasoning group, findRenderer hands it to the timeline
    // and nothing is ever drawn.
    const group = cardGroup(
      await collect([REASONING_START, REASONING_DELTA, CLARIFICATION, STOP])
    );

    expect(group).toBeDefined();
    expect(
      group!.packets.some((p) => p.obj.type === PacketType.REASONING_DELTA)
    ).toBe(false);
    expect(findRenderer({ packets: group!.packets })).toBe(
      UserClarificationRenderer
    );
  });

  test("the stop that ends the paused turn stays out of the card's group", async () => {
    // The pause IS the end of the turn, so the backend sends `stop` right
    // after the card. Landing in the same group would classify it as chat
    // and the text renderer would draw an empty bubble instead.
    const group = cardGroup(await collect([CLARIFICATION, STOP]));

    // `section_end` closing the group is fine; a chat packet would not be.
    expect(
      group!.packets.some(
        (p) =>
          p.obj.type === PacketType.MESSAGE_START ||
          p.obj.type === PacketType.MESSAGE_DELTA ||
          p.obj.type === PacketType.STOP
      )
    ).toBe(false);
    expect(findRenderer({ packets: group!.packets })).toBe(
      UserClarificationRenderer
    );
  });

  test("an answer already streamed before the pause keeps its own bubble", async () => {
    const packets = await collect([
      'data: {"type":"token","content":"Bir bakayım."}\n',
      CLARIFICATION,
      STOP,
    ]);
    const state = processPackets(createInitialState(1), packets);

    const answer = state.potentialDisplayGroups.find((g) =>
      g.packets.some((p) => p.obj.type === PacketType.MESSAGE_DELTA)
    );
    expect(answer).toBeDefined();
    expect(
      answer!.packets.some((p) => p.obj.type === PacketType.USER_CLARIFICATION)
    ).toBe(false);
  });

  test("a reload replays the card after the turn already stopped", async () => {
    // ChatController appends the pending interrupt to the last turn, i.e.
    // after that turn's `stop`. This is the path that already worked; it must
    // keep working.
    const group = cardGroup(
      await collect([
        'data: {"type":"token","content":"Bir bakayım."}\n',
        "data: [DONE]\n",
        CLARIFICATION,
      ])
    );

    expect(findRenderer({ packets: group!.packets })).toBe(
      UserClarificationRenderer
    );
  });

  test("the lock rides in the same group as the card it locks", async () => {
    const group = cardGroup(
      await collect([
        CLARIFICATION,
        'data: {"type":"user_clarification_answered","v":1,"request_id":"int-42","answered":true,"answers":{"Hedef kitle":["Yönetim"]}}\n',
      ])
    );

    expect(
      group!.packets.some(
        (p) => p.obj.type === PacketType.USER_CLARIFICATION_ANSWERED
      )
    ).toBe(true);
    expect(findRenderer({ packets: group!.packets })).toBe(
      UserClarificationRenderer
    );
  });

  test("the pause is answer content even when the turn already reasoned", async () => {
    // THE LIVE BUG. `usePacketProcessor` withholds the display area until it
    // sees a packet that means "answer content is coming". A parked turn never
    // produces one — the model stopped to ask — so with any reasoning or tool
    // step present the card was filtered out and the run looked silently
    // finished. A reload only worked because history reconstruction synthesises
    // a message_start for the trailing steps, which flipped that same gate.
    const packets = await collect([
      REASONING_START,
      REASONING_DELTA,
      CLARIFICATION,
      STOP,
    ]);

    const { result } = renderHook(() => usePacketProcessor(packets, 1));

    // The reasoning really did produce a tool group — this is the condition
    // that used to hide the card, so the test is worthless without it.
    expect(result.current.toolGroups.length).toBeGreaterThan(0);
    expect(result.current.finalAnswerComing).toBe(true);
    expect(
      result.current.displayGroups.some((g) =>
        g.packets.some((p) => p.obj.type === PacketType.USER_CLARIFICATION)
      )
    ).toBe(true);
  });

  test("a HumanInput pause after reasoning is not withheld either", async () => {
    // Same defect, same seam: the flow canvas' pause had it too.
    const packets = await collect([
      REASONING_START,
      REASONING_DELTA,
      'data: {"type":"human_input","node_id":"hi-1","prompt":"Yayınlansın mı?","decisions":["Evet"]}\n',
      STOP,
    ]);

    const { result } = renderHook(() => usePacketProcessor(packets, 1));

    expect(result.current.toolGroups.length).toBeGreaterThan(0);
    expect(
      result.current.displayGroups.some((g) =>
        g.packets.some((p) => p.obj.type === PacketType.HUMAN_INPUT)
      )
    ).toBe(true);
  });
});
