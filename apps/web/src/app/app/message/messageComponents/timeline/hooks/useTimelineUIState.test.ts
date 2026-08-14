/**
 * @jest-environment jsdom
 */

import { renderHook } from "@testing-library/react";
import { Packet, PacketType } from "@/app/app/services/streamingModels";
import { useTimelineUIState, TimelineUIState } from "./useTimelineUIState";

describe("useTimelineUIState", () => {
  const baseInput = {
    stopPacketSeen: false,
    hasPackets: true,
    hasDisplayContent: true,
    userStopped: false,
    isExpanded: true,
    lastTurnGroup: undefined,
    lastStep: undefined,
    lastStepSupportsCollapsedStreaming: true,
    lastStepHasCollapsedContent: true,
    lastStepIsResearchAgent: false,
    parallelActiveStepSupportsCollapsedStreaming: false,
    parallelActiveStepHasCollapsedContent: false,
    isGeneratingImage: false,
    finalAnswerComing: true,
  };

  test("does NOT show Done step when thinking is still actively streaming", () => {
    const packets: Packet[] = [
      {
        placement: { turn_index: 0, tab_index: 0 },
        obj: { type: "reasoning_start" },
      },
      {
        placement: { turn_index: 0, tab_index: 0 },
        obj: {
          type: "reasoning_delta",
          reasoning: "Thinking in progress...",
        },
      },
    ];

    const activeReasoningStep = {
      key: "0-0",
      turnIndex: 0,
      tabIndex: 0,
      packets,
    };

    const { result } = renderHook(() =>
      useTimelineUIState({
        ...baseInput,
        lastStep: activeReasoningStep,
        hasDisplayContent: false,
      })
    );

    expect(result.current.showDoneStep).toBe(false);
    expect(result.current.uiState).toBe(TimelineUIState.STREAMING_SEQUENTIAL);
  });

  test("shows Done step once thinking has finished (SECTION_END received)", () => {
    const packets: Packet[] = [
      {
        placement: { turn_index: 0, tab_index: 0 },
        obj: { type: "reasoning_start" },
      },
      {
        placement: { turn_index: 0, tab_index: 0 },
        obj: { type: "reasoning_delta", reasoning: "Thinking done." },
      },
      {
        placement: { turn_index: 0, tab_index: 0 },
        obj: { type: "section_end" },
      },
    ];

    const completedReasoningStep = {
      key: "0-0",
      turnIndex: 0,
      tabIndex: 0,
      packets,
    };

    const { result } = renderHook(() =>
      useTimelineUIState({
        ...baseInput,
        lastStep: completedReasoningStep,
      })
    );

    expect(result.current.showDoneStep).toBe(true);
    expect(result.current.uiState).toBe(TimelineUIState.COMPLETED_EXPANDED);
  });
  test("shows Done step for reasoning step once display content arrives", () => {
    const activeReasoningStep = {
      key: "0-0",
      turnIndex: 0,
      tabIndex: 0,
      packets: [
        {
          placement: { turn_index: 0, tab_index: 0 },
          obj: { type: PacketType.REASONING_START },
        },
        {
          placement: { turn_index: 0, tab_index: 0 },
          obj: { type: PacketType.REASONING_DELTA, reasoning: "Thinking in progress..." },
        },
      ],
    };

    const { result } = renderHook(() =>
      useTimelineUIState({
        ...baseInput,
        lastStep: activeReasoningStep,
        hasDisplayContent: true,
        finalAnswerComing: true,
      })
    );

    expect(result.current.showDoneStep).toBe(true);
    expect(result.current.uiState).toBe(TimelineUIState.COMPLETED_EXPANDED);
  });
});