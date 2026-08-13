/**
 * Mirrors how AgentMessage composes usePacketProcessor + usePacedTurnGroups,
 * and feeds it packets one at a time the way a live stream does.
 *
 * What matters here is *when* a display group first becomes visible: the text
 * renderer only animates if it mounts while the stream is still open. A group
 * that first appears on the STOP packet renders its whole content instantly.
 */
import { act, renderHook } from "@testing-library/react";
import { Packet, PacketType } from "@/app/app/services/streamingModels";
import { usePacketProcessor } from "./usePacketProcessor";
import { usePacedTurnGroups } from "./usePacedTurnGroups";
import { withPinnedDocumentGroups } from "./packetProcessor";

function useAgentMessageDisplay(packets: Packet[]) {
  const { displayGroups, toolTurnGroups, stopPacketSeen, finalAnswerComing } =
    usePacketProcessor(packets, 1);

  const { pacedDisplayGroups } = usePacedTurnGroups(
    toolTurnGroups,
    displayGroups,
    stopPacketSeen,
    1,
    finalAnswerComing
  );

  const visible = withPinnedDocumentGroups(displayGroups, pacedDisplayGroups);
  return { visible, stopPacketSeen };
}

function packet(
  type: PacketType,
  turn: number,
  obj: Record<string, unknown> = {}
): Packet {
  return {
    placement: { turn_index: turn, tab_index: 0 },
    obj: { type, ...obj },
  } as Packet;
}

const REASONING_START = packet(PacketType.REASONING_START, 1);
const REASONING_DELTA = packet(PacketType.REASONING_DELTA, 1, {
  reasoning: "Rapor hazırlamalıyım",
});
const GENERATION_START = packet(PacketType.DOCUMENT_GENERATION_START, 2, {
  tool_name: "create_document",
  filename: null,
  format: null,
  phase: "writing",
});
const GENERATION_PROGRESS = packet(PacketType.DOCUMENT_GENERATION_PROGRESS, 2, {
  tool_name: "create_document",
  filename: "rapor",
  format: "pdf",
  phase: "writing",
  chars: 900,
});
const GENERATED_FILE = packet(PacketType.GENERATED_FILE, 2, {
  file_id: "abc123",
  filename: "rapor.pdf",
  mime_type: "application/pdf",
  size_bytes: 42,
  download_url: "/api/chat/file/abc123?download=1",
});
const GENERATION_END = packet(PacketType.DOCUMENT_GENERATION_END, 2, {
  tool_name: "create_document",
  filename: "rapor.pdf",
  format: "pdf",
  status: "success",
  error: null,
});
const MESSAGE_START = packet(PacketType.MESSAGE_START, 3, {
  id: "msg-1",
  content: "",
  final_documents: null,
});
const messageDelta = (content: string) =>
  packet(PacketType.MESSAGE_DELTA, 3, { content });
const STOP = packet(PacketType.STOP, 3, { stop_reason: "finished" });

/** Feed packets one at a time, recording what is visible after each. */
function stream(packets: Packet[]) {
  const delivered: Packet[] = [];
  const { result, rerender } = renderHook(
    ({ p }: { p: Packet[] }) => useAgentMessageDisplay(p),
    { initialProps: { p: [] as Packet[] } }
  );

  const steps: { turns: number[]; stopSeen: boolean }[] = [];
  for (const next of packets) {
    delivered.push(next);
    act(() => {
      rerender({ p: [...delivered] });
    });
    steps.push({
      turns: result.current.visible.map((g) => g.turn_index),
      stopSeen: result.current.stopPacketSeen,
    });
  }
  return steps;
}

describe("display visibility during a document generation", () => {
  const FLOW = [
    REASONING_START,
    REASONING_DELTA,
    GENERATION_START,
    GENERATION_PROGRESS,
    GENERATED_FILE,
    GENERATION_END,
    MESSAGE_START,
    messageDelta("Raporunuz"),
    messageDelta(" hazır."),
    STOP,
  ];

  test("the skeleton is visible from the first generation packet", () => {
    const steps = stream(FLOW);

    // index 2 is GENERATION_START
    expect(steps[2]!.turns).toContain(2);
  });

  test("the file card stays visible after the generation closes", () => {
    const steps = stream(FLOW);

    expect(steps[5]!.turns).toContain(2); // GENERATION_END
  });

  test("the file card is never withheld while later steps are paced in", () => {
    const searchStart = packet(PacketType.SEARCH_TOOL_START, 4, {
      is_internet_search: true,
    });
    const steps = stream([
      REASONING_START,
      REASONING_DELTA,
      GENERATION_START,
      GENERATED_FILE,
      GENERATION_END,
      searchStart,
    ]);

    // A tool step revealed after the file must not take the card off screen.
    expect(steps[steps.length - 1]!.turns).toContain(2);
  });

  test("the answer text becomes visible while the stream is still open", () => {
    const steps = stream(FLOW);

    // The answer group (turn 3) must appear before STOP, or MessageTextRenderer
    // mounts with animate=false and dumps the whole answer at once.
    const firstAnswerStep = steps.findIndex((s) => s.turns.includes(3));
    expect(firstAnswerStep).toBeGreaterThanOrEqual(0);
    expect(steps[firstAnswerStep]!.stopSeen).toBe(false);
  });
});
