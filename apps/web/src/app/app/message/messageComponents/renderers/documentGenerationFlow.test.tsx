/**
 * End-to-end wiring for the document generation skeleton.
 *
 * The skeleton only reaches the screen if four independent pieces agree: the
 * SSE layer keeps the generation on one turn, the processor classifies that
 * turn as display content and un-hides it, and the renderer lookup routes the
 * group to GeneratedFileRenderer. Each is unit-tested on its own; this test
 * pins the path through all of them.
 */
import { Packet, PacketType } from "@/app/app/services/streamingModels";
import { handleSSEStream } from "@/lib/search/streamingUtils";
import {
  createInitialState,
  processPackets,
} from "@/app/app/message/messageComponents/timeline/hooks/packetProcessor";
import { findRenderer } from "@/app/app/message/messageComponents/renderMessageComponent";
import GeneratedFileRenderer from "@/app/app/message/messageComponents/renderers/GeneratedFileRenderer";

const REASONING =
  'data: {"type":"reasoning_start"}\n' +
  'data: {"type":"reasoning_delta","reasoning":"Rapor hazırlamalıyım"}\n';

const GENERATION_START =
  'data: {"type":"document_generation_start","tool_name":"create_document","filename":null,"format":null,"phase":"writing"}\n';

const GENERATION_PROGRESS =
  'data: {"type":"document_generation_progress","tool_name":"create_document","filename":"rapor","format":"pdf","phase":"writing","chars":900}\n';

const GENERATED_FILE =
  'data: {"type":"generated_file","file_id":"abc123","filename":"rapor.pdf","mime_type":"application/pdf","size_bytes":42,"download_url":"/api/chat/file/abc123?download=1"}\n';

const GENERATION_END =
  'data: {"type":"document_generation_end","tool_name":"create_document","filename":"rapor.pdf","format":"pdf","status":"success","error":null}\n';

const ANSWER =
  'data: {"type":"token","content":"Raporunuz hazır."}\n' + "data: [DONE]\n";

// Minimal stand-in for a streaming Response: jsdom has no ReadableStream, and
// handleSSEStream only ever touches `body.getReader()`.
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

function displayGroups(packets: Packet[]) {
  return processPackets(createInitialState(1), packets).potentialDisplayGroups;
}

describe("document generation flow", () => {
  test("while writing, the generation is a visible display group of its own", async () => {
    const packets = await collect([
      REASONING,
      GENERATION_START,
      GENERATION_PROGRESS,
    ]);
    const state = processPackets(createInitialState(1), packets);

    // Display content is hidden until the final answer is coming — the
    // generation has to count as such, or the skeleton never renders.
    expect(state.finalAnswerComing).toBe(true);
    expect(state.documentGenerationInFlight).toBe(true);
    expect(state.potentialDisplayGroups).toHaveLength(1);

    const group = state.potentialDisplayGroups[0]!;
    expect(group.packets.map((p) => p.obj.type)).toEqual([
      PacketType.DOCUMENT_GENERATION_START,
      PacketType.DOCUMENT_GENERATION_PROGRESS,
    ]);
    expect(findRenderer({ packets: group.packets })).toBe(
      GeneratedFileRenderer
    );
  });

  test("the finished file joins the group the skeleton was rendered in", async () => {
    const packets = await collect([
      REASONING,
      GENERATION_START,
      GENERATION_PROGRESS,
      GENERATED_FILE,
      GENERATION_END,
      ANSWER,
    ]);
    const groups = displayGroups(packets);

    const fileGroup = groups.find((group) =>
      group.packets.some((p) => p.obj.type === PacketType.GENERATED_FILE)
    );
    expect(fileGroup).toBeDefined();
    // Same group as the skeleton: the card replaces it rather than stacking.
    expect(
      fileGroup!.packets.some(
        (p) => p.obj.type === PacketType.DOCUMENT_GENERATION_START
      )
    ).toBe(true);
    expect(findRenderer({ packets: fileGroup!.packets })).toBe(
      GeneratedFileRenderer
    );
  });

  test("a generation started mid-sentence does not cut the answer in two", async () => {
    // Local models routinely start the tool call in the middle of a word
    // ("…dosyasına dönü" + "ştürüyorum"). Splitting the answer there left one
    // half above the file card and the other below it.
    const packets = await collect([
      'data: {"type":"token","content":"Bunu docx dosyasına dönü"}\n',
      GENERATION_START,
      GENERATION_PROGRESS,
      'data: {"type":"token","content":"ştürüyorum."}\n',
      GENERATED_FILE,
      GENERATION_END,
      "data: [DONE]\n",
    ]);
    const groups = displayGroups(packets);

    const textGroups = groups.filter((group) =>
      group.packets.some((p) => p.obj.type === PacketType.MESSAGE_DELTA)
    );
    expect(textGroups).toHaveLength(1);

    const text = textGroups[0]!.packets
      .filter((p) => p.obj.type === PacketType.MESSAGE_DELTA)
      .map((p) => (p.obj as { content: string }).content)
      .join("");
    expect(text).toBe("Bunu docx dosyasına dönüştürüyorum.");

    // The file still gets its own group, rendered after that text.
    const fileGroup = groups.find((group) =>
      group.packets.some((p) => p.obj.type === PacketType.GENERATED_FILE)
    );
    expect(fileGroup).toBeDefined();
    expect(fileGroup).not.toBe(textGroups[0]);
    expect(groups.indexOf(fileGroup!)).toBeGreaterThan(
      groups.indexOf(textGroups[0]!)
    );
    expect(findRenderer({ packets: fileGroup!.packets })).toBe(
      GeneratedFileRenderer
    );
  });

  test("the answer text after the file is a separate display group", async () => {
    const packets = await collect([
      GENERATION_START,
      GENERATED_FILE,
      GENERATION_END,
      ANSWER,
    ]);
    const groups = displayGroups(packets);

    expect(groups).toHaveLength(2);
    expect(
      groups.some((group) =>
        group.packets.some((p) => p.obj.type === PacketType.MESSAGE_DELTA)
      )
    ).toBe(true);
  });
});
