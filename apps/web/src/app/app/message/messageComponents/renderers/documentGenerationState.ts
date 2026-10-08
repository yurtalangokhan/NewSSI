import {
  DocumentGenerationEnd,
  DocumentGenerationPhase,
  DocumentGenerationProgress,
  DocumentGenerationStart,
  GeneratedFilePacket,
  GenerationChange,
  PacketType,
} from "@/lib/api/domains/chat/streaming-types";

export interface GenerationState {
  started: boolean;
  phase: DocumentGenerationPhase;
  operation: string | null;
  documentId: string | null;
  filename: string | null;
  format: string | null;
  chars: number;
  applied: number | null;
  total: number | null;
  changes: GenerationChange[];
  end: DocumentGenerationEnd | null;
}

const changeKey = (c: GenerationChange) =>
  `${c.kind}\u0000${c.label}\u0000${c.change}`;

// The list is append-only, so an entry's occurrence among identical ones is a
// stable key: a section can gain several blocks of one kind.
export function keyedChanges(changes: GenerationChange[]) {
  const seen = new Map<string, number>();
  return changes.map((change) => {
    const base = `${change.kind}-${change.label}-${change.change}`;
    const occurrence = seen.get(base) ?? 0;
    seen.set(base, occurrence + 1);
    return { change, key: `${base}-${occurrence}` };
  });
}

function mergeChanges(
  known: GenerationChange[],
  next: GenerationChange[] | undefined
) {
  if (!next?.length) return known;
  const seen = new Set(known.map(changeKey));
  return [...known, ...next.filter((c) => !seen.has(changeKey(c)))];
}

/**
 * Collapse the generation lifecycle packets into the current state.
 *
 * Metadata arrives as soon as the model streams it, so a late packet never
 * overwrites a known value with null. `document_id` in particular may be
 * missing on the first chunk and is read from whichever packet carries it.
 */
export function readGenerationState(
  packets: GeneratedFilePacket[]
): GenerationState {
  const state: GenerationState = {
    started: false,
    phase: "writing",
    operation: null,
    documentId: null,
    filename: null,
    format: null,
    chars: 0,
    applied: null,
    total: null,
    changes: [],
    end: null,
  };

  for (const { obj } of packets) {
    if (
      obj.type !== PacketType.DOCUMENT_GENERATION_START &&
      obj.type !== PacketType.DOCUMENT_GENERATION_PROGRESS &&
      obj.type !== PacketType.DOCUMENT_GENERATION_END
    ) {
      continue;
    }
    const base = obj as
      | DocumentGenerationStart
      | DocumentGenerationProgress
      | DocumentGenerationEnd;
    state.documentId = state.documentId ?? base.document_id ?? null;
    state.operation = base.operation ?? state.operation;
    state.filename = base.filename ?? state.filename;
    state.format = base.format ?? state.format;

    switch (obj.type) {
      case PacketType.DOCUMENT_GENERATION_START: {
        const start = obj as DocumentGenerationStart;
        state.started = true;
        state.phase = start.phase ?? "writing";
        // A fresh attempt supersedes the previous one (the agent retries
        // after a rejected tool call).
        state.end = null;
        state.chars = 0;
        state.applied = null;
        state.total = null;
        state.changes = [];
        break;
      }
      case PacketType.DOCUMENT_GENERATION_PROGRESS: {
        const progress = obj as DocumentGenerationProgress;
        state.started = true;
        state.phase = progress.phase ?? state.phase;
        state.chars = Math.max(state.chars, progress.chars ?? 0);
        state.applied = progress.applied ?? state.applied;
        state.total = progress.total ?? state.total;
        state.changes = mergeChanges(state.changes, progress.changes);
        break;
      }
      case PacketType.DOCUMENT_GENERATION_END:
        state.end = obj as DocumentGenerationEnd;
        break;
    }
  }

  return state;
}
