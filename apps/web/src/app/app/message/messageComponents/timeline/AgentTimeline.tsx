"use client";

import React, { useMemo, useCallback } from "react";
import { StopReason } from "@/app/app/services/streamingModels";
import { FullChatState, RenderType } from "../interfaces";
import { TurnGroup } from "./transformers";
import { cn } from "@/lib/utils";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import Text from "@/refresh-components/texts/Text";
import { useTimelineExpansion } from "@/app/app/message/messageComponents/timeline/hooks/useTimelineExpansion";
import { useTimelineMetrics } from "@/app/app/message/messageComponents/timeline/hooks/useTimelineMetrics";
import { useTimelineHeader } from "@/app/app/message/messageComponents/timeline/hooks/useTimelineHeader";
import {
  useTimelineUIState,
  TimelineUIState,
} from "@/app/app/message/messageComponents/timeline/hooks/useTimelineUIState";
import {
  isResearchAgentPackets,
  isSearchToolPackets,
  stepSupportsCollapsedStreaming,
  stepHasCollapsedStreamingContent,
} from "@/app/app/message/messageComponents/timeline/packetHelpers";
import { useTimelineStepState } from "@/app/app/message/messageComponents/timeline/hooks/useTimelineStepState";
import { StreamingHeader } from "@/app/app/message/messageComponents/timeline/headers/StreamingHeader";
import { CompletedHeader } from "@/app/app/message/messageComponents/timeline/headers/CompletedHeader";
import { StoppedHeader } from "@/app/app/message/messageComponents/timeline/headers/StoppedHeader";
import { ParallelStreamingHeader } from "@/app/app/message/messageComponents/timeline/headers/ParallelStreamingHeader";
import { useStreamingStartTime } from "@/app/app/stores/useChatSessionStore";
import { ExpandedTimelineContent } from "./ExpandedTimelineContent";
import { CollapsedStreamingContent } from "./CollapsedStreamingContent";
import { TimelineRoot } from "@/app/app/message/messageComponents/timeline/primitives/TimelineRoot";
import { TimelineHeaderRow } from "@/app/app/message/messageComponents/timeline/primitives/TimelineHeaderRow";
import { useAppBackground } from "@/providers/AppBackgroundProvider";
import { FlowStageSections } from "@/app/app/message/messageComponents/timeline/FlowStageSections";
import {
  getActiveStagePreviewStep,
  type TimelineSection,
} from "@/app/app/message/messageComponents/timeline/hooks/flowStageGrouping";

// =============================================================================
// Private Wrapper Components
// =============================================================================

interface TimelineContainerProps {
  agent: FullChatState["agent"];
  headerContent?: React.ReactNode;
  children?: React.ReactNode;
}

function TimelineContainer({
  agent,
  headerContent,
  children,
}: TimelineContainerProps) {
  return (
    <TimelineRoot>
      <TimelineHeaderRow left={<AgentAvatar agent={agent} size={24} />}>
        {headerContent}
      </TimelineHeaderRow>
      {children}
    </TimelineRoot>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export interface AgentTimelineProps {
  /** Turn groups from usePacketProcessor */
  turnGroups: TurnGroup[];
  /** FlowAgent per-stage timeline sections — rendered inside this same
   *  timeline card, above the inline steps. Empty for every non-flow agent. */
  flowStageSections?: TimelineSection[];
  /** Chat state for rendering content */
  chatState: FullChatState;
  /** Whether the stop packet has been seen */
  stopPacketSeen?: boolean;
  /** Reason for stopping (if stopped) */
  stopReason?: StopReason;
  /** Whether final answer is coming (affects last connector) */
  finalAnswerComing?: boolean;
  /** Whether there is display content after timeline */
  hasDisplayContent?: boolean;
  /** Content to render after timeline (final message + toolbar) - slot pattern */
  children?: React.ReactNode;
  /** Whether the timeline is collapsible */
  collapsible?: boolean;
  /** Title of the button to toggle the timeline */
  buttonTitle?: string;
  /** Test ID for e2e testing */
  "data-testid"?: string;
  /** Processing duration in seconds (for completed messages) */
  processingDurationSeconds?: number;
  /** Whether image generation is in progress */
  isGeneratingImage?: boolean;
  /** Number of images generated */
  generatedImageCount?: number;
  /** Tool processing duration from backend (via MESSAGE_START packet) */
  toolProcessingDuration?: number;
}

/**
 * Custom prop comparison for AgentTimeline memoization.
 * Prevents unnecessary re-renders when parent renders but props haven't meaningfully changed.
 */
function areAgentTimelinePropsEqual(
  prev: AgentTimelineProps,
  next: AgentTimelineProps
): boolean {
  return (
    prev.turnGroups === next.turnGroups &&
    prev.flowStageSections === next.flowStageSections &&
    prev.stopPacketSeen === next.stopPacketSeen &&
    prev.stopReason === next.stopReason &&
    prev.finalAnswerComing === next.finalAnswerComing &&
    prev.hasDisplayContent === next.hasDisplayContent &&
    prev.processingDurationSeconds === next.processingDurationSeconds &&
    prev.collapsible === next.collapsible &&
    prev.buttonTitle === next.buttonTitle &&
    prev.chatState === next.chatState &&
    prev.isGeneratingImage === next.isGeneratingImage &&
    prev.generatedImageCount === next.generatedImageCount &&
    prev.toolProcessingDuration === next.toolProcessingDuration
  );
}

export const AgentTimeline = React.memo(function AgentTimeline({
  turnGroups,
  flowStageSections = [],
  chatState,
  stopPacketSeen = false,
  stopReason,
  finalAnswerComing = false,
  hasDisplayContent = false,
  collapsible = true,
  buttonTitle,
  "data-testid": testId,
  processingDurationSeconds,
  isGeneratingImage = false,
  generatedImageCount = 0,
  toolProcessingDuration,
}: AgentTimelineProps) {
  const { hasBackground } = useAppBackground();

  const hasStageSections = flowStageSections.length > 0;

  // Header text and state flags
  const {
    headerText,
    hasPackets: hasTurnPackets,
    userStopped,
  } = useTimelineHeader(turnGroups, stopReason, isGeneratingImage);
  // Flow stage sections count as timeline content: their presence keeps the
  // timeline out of the bare "Düşünüyor…" EMPTY state and gives it a header.
  const hasPackets = hasTurnPackets || hasStageSections;

  // Memoized metrics derived from turn groups
  const {
    totalSteps,
    isSingleStep,
    lastTurnGroup,
    lastStep,
    lastStepIsResearchAgent,
    lastStepSupportsCollapsedStreaming,
  } = useTimelineMetrics(turnGroups, userStopped);

  // Extract memory text, operation, and whether this is a memory-only timeline
  const { memoryText, memoryOperation, memoryId, memoryIndex, isMemoryOnly } =
    useTimelineStepState(turnGroups);

  // Check if last step is a search tool for INLINE render type
  const lastStepIsSearchTool = useMemo(
    () => lastStep && isSearchToolPackets(lastStep.packets),
    [lastStep]
  );

  const { isExpanded, handleToggle, parallelActiveTab, setParallelActiveTab } =
    useTimelineExpansion(
      stopPacketSeen,
      lastTurnGroup,
      hasDisplayContent,
      // A finished flow run (a reload, or the run just ended) opens with its
      // numbered stage sections visible. While it is still streaming the card
      // stays collapsed and shows a compact live "thinking" peek instead —
      // see `showFlowCollapsedPreview` below.
      hasStageSections && stopPacketSeen
    );

  // Streaming duration tracking
  const streamingStartTime = useStreamingStartTime();

  // Parallel step analysis for collapsed streaming view
  const parallelActiveStep = useMemo(() => {
    if (!lastTurnGroup?.isParallel) return null;
    return (
      lastTurnGroup.steps.find((s) => s.key === parallelActiveTab) ??
      lastTurnGroup.steps[0]
    );
  }, [lastTurnGroup, parallelActiveTab]);

  const parallelActiveStepSupportsCollapsedStreaming = useMemo(() => {
    if (!parallelActiveStep) return false;
    return stepSupportsCollapsedStreaming(parallelActiveStep.packets);
  }, [parallelActiveStep]);

  const lastStepHasCollapsedContent = useMemo(() => {
    if (!lastStep) return false;
    return stepHasCollapsedStreamingContent(lastStep.packets);
  }, [lastStep]);

  const parallelActiveStepHasCollapsedContent = useMemo(() => {
    if (!parallelActiveStep) return false;
    return stepHasCollapsedStreamingContent(parallelActiveStep.packets);
  }, [parallelActiveStep]);

  const stoppedStepsCount = useMemo(() => {
    if (!stopPacketSeen || !userStopped) {
      return totalSteps;
    }

    let count = 0;
    for (const turnGroup of turnGroups) {
      for (const step of turnGroup.steps) {
        if (stepHasCollapsedStreamingContent(step.packets)) {
          count += 1;
        }
      }
    }

    return count;
  }, [stopPacketSeen, userStopped, totalSteps, turnGroups]);

  // Derive all UI state from inputs
  const {
    uiState,
    showCollapsedCompact,
    showCollapsedParallel,
    showParallelTabs,
    showDoneStep,
    showStoppedStep,
    hasDoneIndicator,
    showTintedBackground,
    showRoundedBottom,
  } = useTimelineUIState({
    stopPacketSeen,
    hasPackets,
    hasDisplayContent,
    userStopped,
    isExpanded,
    lastTurnGroup,
    lastStep,
    lastStepSupportsCollapsedStreaming,
    lastStepHasCollapsedContent,
    lastStepIsResearchAgent,
    parallelActiveStepSupportsCollapsedStreaming,
    parallelActiveStepHasCollapsedContent,
    isGeneratingImage,
    finalAnswerComing,
  });

  const headerIsInteractive = useMemo(() => {
    if (!collapsible || isMemoryOnly) {
      return false;
    }

    if (uiState === TimelineUIState.STOPPED) {
      return stoppedStepsCount > 0 || hasStageSections;
    }

    return totalSteps > 0 || hasStageSections;
  }, [
    collapsible,
    isMemoryOnly,
    uiState,
    stoppedStepsCount,
    totalSteps,
    hasStageSections,
  ]);

  // Determine render type override for collapsed streaming view
  const collapsedRenderTypeOverride = useMemo(() => {
    if (lastStepIsResearchAgent) return RenderType.HIGHLIGHT;
    if (lastStepIsSearchTool) return RenderType.INLINE;
    return RenderType.COMPACT;
  }, [lastStepIsResearchAgent, lastStepIsSearchTool]);

  // Collapsed live "thinking" peek for a streaming flow run. Its steps are all
  // folded into numbered FlowStageSections (shown only when expanded), so the
  // collapsed card would otherwise be a bare header until the user expands it.
  // Show the running stage's latest step under the header, exactly the way a
  // non-flow agent's collapsed streaming view works.
  const flowPreviewStep = useMemo(
    () =>
      hasStageSections
        ? getActiveStagePreviewStep(flowStageSections)
        : undefined,
    [hasStageSections, flowStageSections]
  );
  const showFlowCollapsedPreview =
    !isExpanded &&
    !stopPacketSeen &&
    !hasDisplayContent &&
    !showCollapsedCompact &&
    !showCollapsedParallel &&
    !!flowPreviewStep;
  const flowPreviewRenderTypeOverride = useMemo(() => {
    const packets = flowPreviewStep?.packets;
    if (!packets) return RenderType.COMPACT;
    if (isResearchAgentPackets(packets)) return RenderType.HIGHLIGHT;
    if (isSearchToolPackets(packets)) return RenderType.INLINE;
    return RenderType.COMPACT;
  }, [flowPreviewStep]);

  // Header selection based on UI state
  const renderHeader = useCallback(() => {
    switch (uiState) {
      case TimelineUIState.STREAMING_PARALLEL:
        // Only show parallel header when collapsed (showParallelTabs includes !isExpanded check)
        if (showParallelTabs && lastTurnGroup) {
          return (
            <ParallelStreamingHeader
              steps={lastTurnGroup.steps}
              activeTab={parallelActiveTab}
              onTabChange={setParallelActiveTab}
              collapsible={collapsible}
              isExpanded={isExpanded}
              onToggle={handleToggle}
            />
          );
        }
      // falls through to sequential header when expanded or no lastTurnGroup
      case TimelineUIState.STREAMING_SEQUENTIAL:
        return (
          <StreamingHeader
            headerText={headerText}
            collapsible={collapsible}
            buttonTitle={buttonTitle}
            isExpanded={isExpanded}
            onToggle={handleToggle}
            streamingStartTime={streamingStartTime}
            toolProcessingDuration={toolProcessingDuration}
          />
        );

      case TimelineUIState.STOPPED:
        return (
          <StoppedHeader
            totalSteps={stoppedStepsCount}
            collapsible={collapsible}
            isExpanded={isExpanded}
            onToggle={handleToggle}
            hasStageSections={hasStageSections}
          />
        );

      case TimelineUIState.COMPLETED_COLLAPSED:
      case TimelineUIState.COMPLETED_EXPANDED:
        return (
          <CompletedHeader
            totalSteps={totalSteps}
            collapsible={collapsible}
            isExpanded={isExpanded}
            onToggle={handleToggle}
            processingDurationSeconds={
              toolProcessingDuration ?? processingDurationSeconds
            }
            generatedImageCount={generatedImageCount}
            isMemoryOnly={isMemoryOnly}
            memoryText={memoryText}
            memoryOperation={memoryOperation}
            memoryId={memoryId}
            memoryIndex={memoryIndex}
            hasStageSections={hasStageSections}
          />
        );

      default:
        return null;
    }
  }, [
    uiState,
    showParallelTabs,
    lastTurnGroup,
    parallelActiveTab,
    setParallelActiveTab,
    collapsible,
    isExpanded,
    handleToggle,
    headerText,
    buttonTitle,
    streamingStartTime,
    isMemoryOnly,
    memoryText,
    memoryOperation,
    memoryId,
    memoryIndex,
    totalSteps,
    stoppedStepsCount,
    processingDurationSeconds,
    generatedImageCount,
    toolProcessingDuration,
    hasStageSections,
  ]);

  // Empty state: no packets, still streaming, and not stopped
  if (uiState === TimelineUIState.EMPTY) {
    return (
      <TimelineContainer
        agent={chatState.agent}
        headerContent={
          <div className="flex w-full h-full items-center pl-[var(--timeline-header-padding-left)] pr-[var(--timeline-header-padding-right)]">
            <Text
              as="p"
              mainUiAction
              text03
              className="animate-shimmer bg-[length:200%_100%] bg-[linear-gradient(90deg,var(--shimmer-base)_10%,var(--shimmer-highlight)_40%,var(--shimmer-base)_70%)] bg-clip-text text-transparent"
            >
              {headerText}
            </Text>
          </div>
        }
      />
    );
  }

  // Display content only (no timeline steps) - but show header for image generation
  if (uiState === TimelineUIState.DISPLAY_CONTENT_ONLY && !hasStageSections) {
    return <TimelineContainer agent={chatState.agent} />;
  }

  return (
    <TimelineContainer
      agent={chatState.agent}
      headerContent={
        <div
          className={cn(
            "flex flex-1 min-w-0 h-full items-center justify-between p-1 rounded-t-12 transition-colors duration-300",
            headerIsInteractive &&
              (hasBackground
                ? "hover:backdrop-blur-md hover:bg-background-tint-00/60"
                : "hover:bg-background-tint-00"),
            showTintedBackground &&
              (hasBackground
                ? "backdrop-blur-md bg-background-tint-00/60"
                : "bg-background-tint-00"),
            showRoundedBottom && !showFlowCollapsedPreview && "rounded-b-12"
          )}
        >
          {renderHeader()}
        </div>
      }
    >
      {/* Collapsed streaming view - single step compact mode */}
      {showCollapsedCompact && lastStep && (
        <CollapsedStreamingContent
          step={lastStep}
          chatState={chatState}
          stopReason={stopReason}
          renderTypeOverride={collapsedRenderTypeOverride}
        />
      )}

      {/* Collapsed streaming view - parallel tools compact mode */}
      {showCollapsedParallel && parallelActiveStep && (
        <CollapsedStreamingContent
          step={parallelActiveStep}
          chatState={chatState}
          stopReason={stopReason}
          renderTypeOverride={RenderType.HIGHLIGHT}
        />
      )}

      {/* Collapsed streaming view - flow run: peek the running stage's step */}
      {showFlowCollapsedPreview && flowPreviewStep && (
        <CollapsedStreamingContent
          step={flowPreviewStep}
          chatState={chatState}
          stopReason={stopReason}
          renderTypeOverride={flowPreviewRenderTypeOverride}
        />
      )}

      {/* Expanded timeline view */}
      {isExpanded && (
        <div className="animate-in fade-in slide-in-from-top-2 duration-300">
          {/* FlowAgent per-stage sections: numbered, individually-collapsible
              groups for every stage before the ChatOutput-fed one. Part of
              the collapsible body so the timeline's own chevron hides them. */}
          {hasStageSections && (
            <div className="px-2 pb-1">
              <FlowStageSections
                sections={flowStageSections}
                chatState={chatState}
              />
            </div>
          )}
          <ExpandedTimelineContent
            turnGroups={turnGroups}
            chatState={chatState}
            stopPacketSeen={stopPacketSeen}
            stopReason={stopReason}
            isSingleStep={isSingleStep}
            userStopped={userStopped}
            showDoneStep={showDoneStep}
            showStoppedStep={showStoppedStep}
            hasDoneIndicator={hasDoneIndicator}
          />
        </div>
      )}
    </TimelineContainer>
  );
}, areAgentTimelinePropsEqual);

export default AgentTimeline;
