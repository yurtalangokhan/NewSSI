import { useRef, useState, useMemo, useCallback } from "react";
import {
  Packet,
  StreamingCitation,
  StopReason,
} from "@/app/app/services/streamingModels";
import { CitationMap } from "@/app/app/interfaces";
import { OnyxDocument } from "@/lib/search/interfaces";
import {
  ProcessorState,
  GroupedPacket,
  createInitialState,
  isDocumentGroup,
  processPackets,
} from "@/app/app/message/messageComponents/timeline/hooks/packetProcessor";
import {
  transformPacketGroups,
  groupStepsByTurn,
  TurnGroup,
} from "@/app/app/message/messageComponents/timeline/transformers";

export interface UsePacketProcessorResult {
  // Data
  toolGroups: GroupedPacket[];
  displayGroups: GroupedPacket[];
  toolTurnGroups: TurnGroup[];
  citations: StreamingCitation[];
  citationMap: CitationMap;
  documentMap: Map<string, OnyxDocument>;

  // Status (derived from packets)
  stopPacketSeen: boolean;
  stopReason: StopReason | undefined;
  hasSteps: boolean;
  expectedBranchesPerTurn: Map<number, number>;
  isGeneratingImage: boolean;
  generatedImageCount: number;
  // Whether final answer is coming (MESSAGE_START seen)
  finalAnswerComing: boolean;
  // Whether a document/spreadsheet is currently being written or rendered
  documentGenerationInFlight: boolean;
  // Seconds the backend stream has been silent, or null while it produces.
  streamSilentSeconds: number | null;
  // Tool processing duration from backend (via MESSAGE_START packet)
  toolProcessingDuration: number | undefined;

  // Completion: stopPacketSeen && renderComplete
  isComplete: boolean;

  // Callbacks
  onRenderComplete: () => void;
  markAllToolsDisplayed: () => void;
}

/**
 * Hook for processing streaming packets in AgentMessage.
 *
 * Architecture:
 * - Processor state in ref: incremental processing, synchronous, no double render
 * - Only true UI state: renderComplete (set by callback), forceShowAnswer (override)
 * - Everything else derived from packets
 *
 * Key insight: finalAnswerComing and stopPacketSeen are DERIVED from packets,
 * not independent state. Only renderComplete needs useState.
 */
export function usePacketProcessor(
  rawPackets: Packet[],
  nodeId: number
): UsePacketProcessorResult {
  // Processor in ref: incremental, synchronous, no double render
  const stateRef = useRef<ProcessorState>(createInitialState(nodeId));

  // Only TRUE UI state: "has renderer finished?"
  const [renderComplete, setRenderComplete] = useState(false);

  // Optional override to force showing answer
  const [forceShowAnswer, setForceShowAnswer] = useState(false);

  // Last non-empty displayGroups shown while finalAnswerComing was true. A
  // real tool call after some answer text (e.g. a short preamble before
  // "let me search for that") resets finalAnswerComing — without this, the
  // text that was already written gets hidden until the new tool step
  // finishes, then shown again, reading as the text getting written then
  // deleted every time a tool call happens mid-answer.
  // Stored as keys, not as the group objects: the groups are rebuilt on every
  // pass, so holding the objects would pin a snapshot. Tokens that arrive in
  // the same batch as the tool call would then never render — the snapshot
  // predates them and the live groups are not consulted again until the tool
  // phase ends.
  const lastDisplayGroupKeysRef = useRef<Set<string>>(new Set());

  // Reset on nodeId change
  if (stateRef.current.nodeId !== nodeId) {
    stateRef.current = createInitialState(nodeId);
    setRenderComplete(false);
    setForceShowAnswer(false);
    lastDisplayGroupKeysRef.current = new Set();
  }

  // Track for transition detection
  const prevNextPacketIndex = stateRef.current.nextPacketIndex;
  const prevFinalAnswerComing = stateRef.current.finalAnswerComing;

  // Detect stream reset (packets shrunk)
  if (prevNextPacketIndex > rawPackets.length) {
    stateRef.current = createInitialState(nodeId);
    setRenderComplete(false);
    setForceShowAnswer(false);
    lastDisplayGroupKeysRef.current = new Set();
  }

  // Process packets synchronously (incremental) - only if new packets arrived
  if (rawPackets.length > stateRef.current.nextPacketIndex) {
    stateRef.current = processPackets(stateRef.current, rawPackets);
  }

  // Reset renderComplete on tool-after-message transition
  if (prevFinalAnswerComing && !stateRef.current.finalAnswerComing) {
    setRenderComplete(false);
  }

  // Access state directly (result arrays are built in processPackets)
  const state = stateRef.current;

  // Derive displayGroups (not state!)
  const effectiveFinalAnswerComing = state.finalAnswerComing || forceShowAnswer;
  const displayGroups = useMemo(() => {
    if (effectiveFinalAnswerComing || state.toolGroups.length === 0) {
      lastDisplayGroupKeysRef.current = new Set(
        state.potentialDisplayGroups.map((g) => g.key)
      );
      return state.potentialDisplayGroups;
    }
    // Tools resumed after some answer text had already streamed in (e.g. a
    // short preamble before a real tool call) — keep showing that text
    // instead of hiding it while the new tool step plays out, or it flashes
    // away and back on every tool call. A generated file is a finished
    // artifact either way, not answer-in-progress text, so its card (or the
    // skeleton producing it) always stays put regardless.
    const shownKeys = lastDisplayGroupKeysRef.current;
    if (shownKeys.size === 0) {
      return state.potentialDisplayGroups.filter(isDocumentGroup);
    }
    // Re-select from the live groups so text that landed alongside the tool
    // call still appears, rather than serving a stale copy of them.
    return state.potentialDisplayGroups.filter(
      (g) => shownKeys.has(g.key) || isDocumentGroup(g)
    );
  }, [
    effectiveFinalAnswerComing,
    state.toolGroups.length,
    state.potentialDisplayGroups,
  ]);

  // Transform toolGroups to timeline format
  const toolTurnGroups = useMemo(() => {
    const allSteps = transformPacketGroups(state.toolGroups);
    return groupStepsByTurn(allSteps);
  }, [state.toolGroups]);

  // Callback reads from ref: always current value, no ref needed in component
  const onRenderComplete = useCallback(() => {
    if (stateRef.current.finalAnswerComing) {
      setRenderComplete(true);
    }
  }, []);

  const markAllToolsDisplayed = useCallback(() => {
    setForceShowAnswer(true);
  }, []);

  return {
    // Data
    toolGroups: state.toolGroups,
    displayGroups,
    toolTurnGroups,
    citations: state.citations,
    citationMap: state.citationMap,
    documentMap: state.documentMap,

    // Status (derived from packets)
    stopPacketSeen: state.stopPacketSeen,
    stopReason: state.stopReason,
    hasSteps: toolTurnGroups.length > 0,
    expectedBranchesPerTurn: state.expectedBranches,
    isGeneratingImage: state.isGeneratingImage,
    generatedImageCount: state.generatedImageCount,
    finalAnswerComing: state.finalAnswerComing,
    documentGenerationInFlight: state.documentGenerationInFlight,
    streamSilentSeconds: state.streamSilentSeconds,
    toolProcessingDuration: state.toolProcessingDuration,

    // Completion: stopPacketSeen && renderComplete
    isComplete: state.stopPacketSeen && renderComplete,

    // Callbacks
    onRenderComplete,
    markAllToolsDisplayed,
  };
}
