import { readGenerationState } from "@/app/app/message/messageComponents/renderers/documentGenerationState";
import {
  GeneratedFilePacket,
  PacketType,
} from "@/lib/api/domains/chat/streaming-types";

const placement = { turn_index: 0, tab_index: 0 };
const packet = (obj: Record<string, unknown>) =>
  ({ placement, obj }) as unknown as GeneratedFilePacket;

describe("readGenerationState", () => {
  it("reads document_id from a later packet when the first lacks it", () => {
    const state = readGenerationState([
      packet({
        type: PacketType.DOCUMENT_GENERATION_START,
        phase: "writing",
        operation: "edit",
        tool_name: "edit_document",
        filename: null,
        format: null,
      }),
      packet({
        type: PacketType.DOCUMENT_GENERATION_PROGRESS,
        phase: "applying",
        document_id: "d1",
        applied: 1,
        total: 3,
        changes: [{ kind: "paragraph", label: "Amaç", change: "modified" }],
        tool_name: "edit_document",
        filename: "a.docx",
        format: "docx",
      }),
      packet({
        type: PacketType.DOCUMENT_GENERATION_PROGRESS,
        phase: "validating",
        document_id: null,
        applied: 3,
        total: 3,
        changes: [],
        tool_name: "edit_document",
        filename: null,
        format: null,
      }),
    ]);

    expect(state).toMatchObject({
      started: true,
      operation: "edit",
      documentId: "d1",
      phase: "validating",
      applied: 3,
      total: 3,
      filename: "a.docx",
    });
    expect(state.changes).toEqual([
      { kind: "paragraph", label: "Amaç", change: "modified" },
    ]);
  });

  it("accumulates change steps without duplicates", () => {
    const change = { kind: "table", label: "SLA", change: "modified" };
    const state = readGenerationState([
      packet({
        type: PacketType.DOCUMENT_GENERATION_PROGRESS,
        phase: "applying",
        applied: 1,
        total: 2,
        changes: [change],
        tool_name: "t",
        filename: null,
        format: null,
      }),
      packet({
        type: PacketType.DOCUMENT_GENERATION_PROGRESS,
        phase: "applying",
        applied: 2,
        total: 2,
        changes: [
          change,
          { kind: "paragraph", label: "Amaç", change: "modified" },
        ],
        tool_name: "t",
        filename: null,
        format: null,
      }),
    ]);

    expect(state.changes.map((c) => c.label)).toEqual(["SLA", "Amaç"]);
  });

  it("a fresh start resets progress but keeps the document id", () => {
    const state = readGenerationState([
      packet({
        type: PacketType.DOCUMENT_GENERATION_PROGRESS,
        phase: "applying",
        document_id: "d1",
        applied: 1,
        total: 2,
        changes: [],
        chars: 50,
        tool_name: "t",
        filename: null,
        format: null,
      }),
      packet({
        type: PacketType.DOCUMENT_GENERATION_END,
        status: "error",
        error: "x",
        tool_name: "t",
        filename: null,
        format: null,
      }),
      packet({
        type: PacketType.DOCUMENT_GENERATION_START,
        phase: "writing",
        tool_name: "t",
        filename: null,
        format: null,
      }),
    ]);

    expect(state).toMatchObject({
      end: null,
      chars: 0,
      applied: null,
      total: null,
      documentId: "d1",
      phase: "writing",
    });
    expect(state.changes).toEqual([]);
  });

  it("keeps legacy packets working (no operation, no applied)", () => {
    const state = readGenerationState([
      packet({
        type: PacketType.DOCUMENT_GENERATION_START,
        phase: "writing",
        tool_name: "create_document",
        filename: "r.pdf",
        format: "pdf",
      }),
      packet({
        type: PacketType.DOCUMENT_GENERATION_PROGRESS,
        phase: "writing",
        chars: 120,
        tool_name: "create_document",
        filename: null,
        format: null,
      }),
    ]);

    expect(state).toMatchObject({
      operation: null,
      applied: null,
      chars: 120,
      filename: "r.pdf",
    });
  });
});
