"use client";

import React, { useRef, RefObject, useMemo } from "react";
import {
  Packet,
  PacketType,
  StopReason,
} from "@/app/app/services/streamingModels";
import { FullChatState } from "@/app/app/message/messageComponents/interfaces";
import { FeedbackType } from "@/app/app/interfaces";
import { handleCopy } from "@/app/app/message/copyingUtils";
import { useMessageSwitching } from "@/app/app/message/messageComponents/hooks/useMessageSwitching";
import { RendererComponent } from "@/app/app/message/messageComponents/renderMessageComponent";
import { usePacketProcessor } from "@/app/app/message/messageComponents/timeline/hooks/usePacketProcessor";
import { withPinnedDocumentGroups } from "@/app/app/message/messageComponents/timeline/hooks/packetProcessor";
import { usePacedTurnGroups } from "@/app/app/message/messageComponents/timeline/hooks/usePacedTurnGroups";
import MessageToolbar from "@/app/app/message/messageComponents/MessageToolbar";
import { LlmDescriptor, LlmManager } from "@/lib/hooks";
import { AgentId } from "@/app/admin/agents/interfaces";
import { Message } from "@/app/app/interfaces";
import Text from "@/refresh-components/texts/Text";
import { AgentTimeline } from "@/app/app/message/messageComponents/timeline/AgentTimeline";
import GraphStageStrip from "@/app/app/message/messageComponents/timeline/GraphStageStrip";
import { buildStageGroups } from "@/app/app/message/messageComponents/timeline/hooks/flowStageGrouping";
import { useMarkdownRenderer } from "@/app/app/message/messageComponents/markdownUtils";
import { cn } from "@/lib/utils";
import { useAppBackground } from "@/providers/AppBackgroundProvider";
import { useTranslation } from "react-i18next";

// Type for the regeneration factory function passed from ChatUI
export type RegenerationFactory = (regenerationRequest: {
  messageId: number;
  parentMessage: Message;
  forceSearch?: boolean;
  forcedPersonaId?: AgentId | null;
}) => (modelOverride: LlmDescriptor) => Promise<void>;

export interface AgentMessageProps {
  rawPackets?: Packet[];
  packetCount?: number; // Tracked separately for React memo comparison (avoids reading from mutated array)
  chatState: FullChatState;
  nodeId: number;
  messageId?: number;
  currentFeedback?: FeedbackType | null;
  llmManager: LlmManager | null;
  otherMessagesCanSwitchTo?: number[];
  onMessageSelection?: (nodeId: number) => void;
  // Stable regeneration callback - takes (parentMessage) and returns a function that takes (modelOverride)
  onRegenerate?: RegenerationFactory;
  // Parent message needed to construct regeneration request
  parentMessage?: Message | null;
  // persona_id that actually produced this message (for retry-to-same-agent)
  originalPersonaId?: AgentId | null;
  // Duration in seconds for processing this message (agent messages only)
  processingDurationSeconds?: number;
  // Final message text - used as fallback when packets are empty (for historical messages)
  finalMessageText?: string;
}

// TODO: Consider more robust comparisons:
// - `chatState.docs`, `chatState.citations`, and `otherMessagesCanSwitchTo` use
//   reference equality. Shallow array/object comparison would be more robust if
//   these are recreated with the same values.
function arePropsEqual(
  prev: AgentMessageProps,
  next: AgentMessageProps
): boolean {
  return (
    prev.nodeId === next.nodeId &&
    prev.messageId === next.messageId &&
    prev.currentFeedback === next.currentFeedback &&
    // Compare packetCount (primitive) instead of rawPackets.length
    // The array is mutated in place, so reading .length from prev and next would return same value
    prev.packetCount === next.packetCount &&
    prev.chatState.agent?.id === next.chatState.agent?.id &&
    prev.chatState.docs === next.chatState.docs &&
    prev.chatState.citations === next.chatState.citations &&
    prev.chatState.overriddenModel === next.chatState.overriddenModel &&
    prev.chatState.researchType === next.chatState.researchType &&
    prev.otherMessagesCanSwitchTo === next.otherMessagesCanSwitchTo &&
    prev.onRegenerate === next.onRegenerate &&
    prev.parentMessage?.messageId === next.parentMessage?.messageId &&
    prev.originalPersonaId === next.originalPersonaId &&
    prev.llmManager?.isLoadingProviders ===
      next.llmManager?.isLoadingProviders &&
    prev.processingDurationSeconds === next.processingDurationSeconds &&
    prev.finalMessageText === next.finalMessageText
    // Skip: chatState.regenerate, chatState.setPresentingDocument,
    //       most of llmManager, onMessageSelection (function/object props)
  );
}

const AgentMessage = React.memo(function AgentMessage({
  rawPackets = [],
  chatState,
  nodeId,
  messageId,
  currentFeedback,
  llmManager,
  otherMessagesCanSwitchTo,
  onMessageSelection,
  onRegenerate,
  parentMessage,
  originalPersonaId,
  processingDurationSeconds,
  finalMessageText,
  packetCount,
}: AgentMessageProps) {
  const markdownRef = useRef<HTMLDivElement>(null);
  const finalAnswerRef = useRef<HTMLDivElement>(null);
  const { foregroundTextClass, foregroundTextStyle } = useAppBackground();
  const { t } = useTranslation();

  // If packets are empty but we have finalMessageText (historical message),
  // create synthetic packets for rendering
  const effectivePackets = useMemo((): Packet[] => {
    if (rawPackets.length > 0) {
      return rawPackets;
    }
    if (finalMessageText && finalMessageText.length > 0) {
      // Create synthetic MESSAGE_START + MESSAGE_DELTA + STOP packets
      // Using 'as any' to bypass strict typing for synthetic packets
      return [
        {
          placement: { turn_index: 0, sub_turn_index: null },
          obj: {
            id: `historical-${nodeId}`,
            type: "message_start",
            content: finalMessageText,
            final_documents: null,
          },
        } as unknown as Packet,
        {
          placement: { turn_index: 0, sub_turn_index: null },
          obj: {
            type: "message_delta",
            content: finalMessageText,
          },
        } as unknown as Packet,
        // Include STOP packet to mark completion
        {
          placement: { turn_index: 0, sub_turn_index: null },
          obj: {
            type: "stop",
            stop_reason: "finished",
          },
        } as unknown as Packet,
      ];
    }
    return rawPackets;
  }, [rawPackets, finalMessageText]);

  const hasGraphStagePackets = useMemo(
    () =>
      effectivePackets.some(
        (packet) =>
          packet.obj.type === PacketType.GRAPH_STAGE_START ||
          packet.obj.type === PacketType.GRAPH_STAGE_END
      ),
    // effectivePackets is mutated in place (stable ref) — key on length/count
    // or a stage packet arriving after the first render is never noticed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [effectivePackets, effectivePackets.length, packetCount]
  );

  // FlowAgent per-stage timeline (folded, computed below from the SHARED
  // pipeline's turn groups so citations / sources / file cards stay intact).
  // First: if the run ended with no real answer packet (a ConditionalRouter
  // topology the backend couldn't mark final), splice a synthetic answer so
  // the bubble renders and the message completes. Only safe at `stop` — no
  // more real packets append, so the synthetic tail keeps a stable index for
  // the incremental packet processor. The mid-run equivalent
  // (`liveFinalAnswerText`) is rendered directly below instead.
  const preScan = useMemo(
    () => buildStageGroups([], effectivePackets),
    [effectivePackets, effectivePackets.length]
  );
  const timelinePackets = useMemo(() => {
    if (!preScan.fallbackAnswerText) return effectivePackets;
    const at = { turn_index: 100_000, sub_turn_index: null };
    return [
      ...effectivePackets,
      {
        placement: at,
        obj: { type: "message_start", content: "", final_documents: null },
      },
      {
        placement: at,
        obj: { type: "message_delta", content: preScan.fallbackAnswerText },
      },
      { placement: at, obj: { type: "stop", stop_reason: "finished" } },
    ] as unknown as Packet[];
  }, [effectivePackets, effectivePackets.length, preScan.fallbackAnswerText]);

  // Process streaming packets: returns data and callbacks
  // Hook handles all state internally, exposes clean API
  const {
    citations,
    citationMap,
    documentMap,
    toolGroups,
    toolTurnGroups,
    displayGroups,
    hasSteps,
    stopPacketSeen,
    stopReason,
    isGeneratingImage,
    generatedImageCount,
    isComplete,
    onRenderComplete,
    finalAnswerComing,
    streamSilentSeconds,
    toolProcessingDuration,
  } = usePacketProcessor(timelinePackets, nodeId);

  // Apply pacing delays between different tool types for smoother visual transitions
  const { pacedTurnGroups, pacedDisplayGroups, pacedFinalAnswerComing } =
    usePacedTurnGroups(
      toolTurnGroups,
      displayGroups,
      stopPacketSeen,
      nodeId,
      finalAnswerComing
    );

  // Fold the FlowAgent stages: split the paced timeline steps into numbered
  // per-stage sections (intermediate stages) + the steps that stay inline
  // (final answer stage, un-attributed). The shared pipeline above already
  // built citations / sources / documents from every packet.
  //
  // `packetCount` / `effectivePackets.length` are explicit deps: `timelinePackets`
  // is the stream's mutated-in-place array (stable reference), and a stage's
  // folded `flow_stage_output_delta` packets are excluded from `pacedTurnGroups`
  // — so without a length signal here this memo would not recompute while an
  // intermediate stage streams its output, and the "Çıktı" block would only
  // update once some other packet (a tool step, `flow_stage_end`) forced it.
  const { sections: flowStageSections, inlineTurnGroups } = useMemo(
    () => buildStageGroups(pacedTurnGroups, timelinePackets),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pacedTurnGroups, timelinePackets, packetCount, effectivePackets.length]
  );

  // The generation skeleton and the file card it turns into are never withheld
  // by step pacing — they would blink out whenever another step is revealed.
  const visibleDisplayGroups = useMemo(
    () => withPinnedDocumentGroups(displayGroups, pacedDisplayGroups),
    [displayGroups, pacedDisplayGroups]
  );

  // Memoize merged citations separately to avoid creating new object when neither source changed
  const mergedCitations = useMemo(
    () => ({
      ...chatState.citations,
      ...citationMap,
    }),
    [chatState.citations, citationMap]
  );

  // Create a chatState that uses streaming citations for immediate rendering
  // This merges the prop citations with streaming citations, preferring streaming ones
  // Memoized with granular dependencies to prevent cascading re-renders
  // Note: chatState object is recreated upstream on every render, so we depend on
  // individual fields instead of the whole object for proper memoization
  const effectiveChatState = useMemo<FullChatState>(
    () => ({
      ...chatState,
      citations: mergedCitations,
    }),
    [
      chatState.agent,
      chatState.docs,
      chatState.setPresentingDocument,
      chatState.overriddenModel,
      chatState.researchType,
      mergedCitations,
    ]
  );

  // Message switching logic
  const {
    currentMessageInd,
    includeMessageSwitcher,
    getPreviousMessage,
    getNextMessage,
  } = useMessageSwitching({
    nodeId,
    otherMessagesCanSwitchTo,
    onMessageSelection,
  });

  // Live answer for a flow whose final node sits on a loop cycle: the backend
  // folds every iteration's output (it can't know which is last), so no real
  // `token` packets reach the bubble. Render the current iteration's folded
  // text here directly — splicing synthetic packets would shift indices under
  // the incremental packet processor while real packets are still arriving.
  // At `stop` the `fallbackAnswerText` splice above takes over with the same
  // text, so `visibleDisplayGroups` then carries the answer and this hides.
  const showLiveFinalAnswer =
    !stopPacketSeen &&
    visibleDisplayGroups.length === 0 &&
    preScan.liveFinalAnswerText.trim().length > 0;
  const { renderedContent: liveFinalAnswerRendered } = useMarkdownRenderer(
    showLiveFinalAnswer ? preScan.liveFinalAnswerText + " [*]() " : "",
    effectiveChatState,
    "font-main-content-body",
    foregroundTextStyle
  );

  return (
    <div
      className="flex flex-col gap-3 rounded-12 py-1"
      data-testid={isComplete ? "onyx-ai-message" : undefined}
    >
      {/* graph_stage_start/end packets only ever exist in-memory for the
          turn that's actually streaming — a page refresh replays historical
          messages from finalMessageText alone, with no such packets to
          reconstruct from. A flow-backed agent's strip still has something
          worth showing then (the flow's own structure, fetched by
          definition id rather than derived from packets), so it stays
          mounted regardless of packet history; a classic stage/sub_agent
          agent has no such fallback and keeps the original packet-driven
          gate. */}
      {(hasGraphStagePackets ||
        !isComplete ||
        chatState.agent?.graph_schema === "flow") && (
        <GraphStageStrip
          agent={chatState.agent}
          packets={effectivePackets}
          packetCount={packetCount ?? effectivePackets.length}
        />
      )}

      {/* Row 1: Two-column layout for tool steps */}

      <AgentTimeline
        turnGroups={inlineTurnGroups}
        flowStageSections={flowStageSections}
        chatState={effectiveChatState}
        stopPacketSeen={stopPacketSeen}
        stopReason={stopReason}
        hasDisplayContent={visibleDisplayGroups.length > 0}
        processingDurationSeconds={processingDurationSeconds}
        isGeneratingImage={isGeneratingImage}
        generatedImageCount={generatedImageCount}
        finalAnswerComing={pacedFinalAnswerComing}
        toolProcessingDuration={toolProcessingDuration}
      />

      {/* Row 2: Display content + MessageToolbar */}
      <div
        ref={markdownRef}
        className={cn(
          "overflow-x-visible focus:outline-none select-text cursor-text rounded-12 px-3 py-1 transition-colors",
          foregroundTextClass
        )}
        onCopy={(e) => {
          if (markdownRef.current) {
            handleCopy(e, markdownRef as RefObject<HTMLDivElement>);
          }
        }}
      >
        {showLiveFinalAnswer && (
          <div ref={finalAnswerRef} data-testid="live-final-answer">
            {liveFinalAnswerRendered}
          </div>
        )}
        {visibleDisplayGroups.length > 0 && (
          <div ref={finalAnswerRef}>
            {visibleDisplayGroups.map((displayGroup, index) => (
              <RendererComponent
                key={displayGroup.key}
                packets={displayGroup.packets}
                chatState={effectiveChatState}
                onComplete={() => {
                  // Only mark complete on the last display group
                  // Hook handles the finalAnswerComing check internally
                  if (index === visibleDisplayGroups.length - 1) {
                    onRenderComplete();
                  }
                }}
                animate={!stopPacketSeen}
                stopPacketSeen={stopPacketSeen}
                stopReason={stopReason}
              >
                {(results) => (
                  <>
                    {results.map((r, i) => (
                      <div key={i}>{r.content}</div>
                    ))}
                  </>
                )}
              </RendererComponent>
            ))}
          </div>
        )}
        {/* The backend stream can go quiet for minutes: Ollama withholds
            tool-call arguments until the call is complete, so a model writing
            a document reports nothing meanwhile. Show that work continues
            rather than leaving the answer looking frozen. */}
        {streamSilentSeconds !== null && !stopPacketSeen && (
          // Same shimmer the timeline header uses while streaming, so a quiet
          // stretch reads as the same "working" state rather than a new kind
          // of message. No color class or inline color here: the gradient is
          // painted through the glyphs, which needs the text transparent.
          <Text
            as="p"
            secondaryBody
            className="animate-shimmer mt-1 bg-[length:200%_100%] bg-[linear-gradient(90deg,var(--shimmer-base)_10%,var(--shimmer-highlight)_40%,var(--shimmer-base)_70%)] bg-clip-text text-transparent"
          >
            {t("agentMessage.stillWorking", { seconds: streamSilentSeconds })}
          </Text>
        )}
        {/* Show stopped message when user cancelled and no display content */}
        {visibleDisplayGroups.length === 0 &&
          stopReason === StopReason.USER_CANCELLED && (
            <Text
              as="p"
              secondaryBody
              text04
              className={foregroundTextClass}
              style={foregroundTextStyle}
            >
              User has stopped generation
            </Text>
          )}
      </div>

      {/* Feedback buttons - only show when streaming and rendering complete */}
      {isComplete && (
        <MessageToolbar
          nodeId={nodeId}
          messageId={messageId}
          includeMessageSwitcher={includeMessageSwitcher}
          currentMessageInd={currentMessageInd}
          otherMessagesCanSwitchTo={otherMessagesCanSwitchTo}
          getPreviousMessage={getPreviousMessage}
          getNextMessage={getNextMessage}
          onMessageSelection={onMessageSelection}
          rawPackets={rawPackets}
          finalAnswerRef={finalAnswerRef}
          currentFeedback={currentFeedback}
          onRegenerate={onRegenerate}
          parentMessage={parentMessage}
          llmManager={llmManager}
          currentModelName={chatState.overriddenModel}
          originalPersonaId={originalPersonaId}
          citations={citations}
          documentMap={documentMap}
        />
      )}
    </div>
  );
}, arePropsEqual);

export default AgentMessage;
