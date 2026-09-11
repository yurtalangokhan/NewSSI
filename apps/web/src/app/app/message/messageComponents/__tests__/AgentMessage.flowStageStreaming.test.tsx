/**
 * Regression: an intermediate FlowAgent stage's folded output ("Çıktı" block)
 * must grow as `flow_stage_output_delta` packets arrive.
 *
 * The stream layer mutates ONE packet array in place and bumps `packetCount`.
 * `timelinePackets` therefore keeps a stable reference, and folded
 * `flow_stage_output_delta` packets never reach `pacedTurnGroups` — so the
 * `flowStageSections` memo needs `packetCount` in its deps, or the block only
 * updates once an unrelated packet forces a recompute (looked like "the output
 * isn't streamed, it just appears at once").
 */
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

jest.mock("@/providers/AppBackgroundProvider", () => ({
  useAppBackground: () => ({
    hasBackground: false,
    foregroundTextClass: "",
    foregroundTextStyle: {},
    foregroundMutedTextClass: "",
    foregroundMutedTextStyle: {},
  }),
}));
jest.mock("@/app/app/stores/useChatSessionStore", () => ({
  useStreamingStartTime: () => null,
  useChatSessionStore: {
    getState: () => ({ getStreamingStartTime: () => null }),
  },
}));
jest.mock("@/app/app/message/copyingUtils", () => ({
  handleCopy: () => undefined,
}));
jest.mock("../renderMessageComponent", () => ({
  RendererComponent: () => null,
}));
jest.mock("../MessageToolbar", () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock("../timeline/GraphStageStrip", () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock("../hooks/useMessageSwitching", () => ({
  useMessageSwitching: () => ({
    currentMessageInd: 0,
    includeMessageSwitcher: false,
    getPreviousMessage: () => undefined,
    getNextMessage: () => undefined,
  }),
}));

import AgentMessage from "../AgentMessage";

const chatState = {
  agent: { id: 1, name: "Flow", graph_schema: "flow" },
  citations: {},
} as any;

const llmManager = { isLoadingProviders: false } as any;

function renderMsg(packets: any[]) {
  return (
    <AgentMessage
      rawPackets={packets}
      packetCount={packets.length}
      chatState={chatState}
      nodeId={1}
      messageId={1}
      llmManager={llmManager}
    />
  );
}

function fsPacket(type: string, extra: Record<string, unknown> = {}) {
  return {
    placement: {
      turn_index: 0,
      sub_turn_index: null,
      stage_key: "R#1",
      stage_order: 1,
      iteration: 1,
      is_final_stage: false,
      ...(extra.placement as object),
    },
    obj: { type, stage_key: "R#1", stage_order: 1, iteration: 1, ...extra },
  } as any;
}

function stagePacket(
  type: string,
  stageKey: string,
  order: number,
  extra: Record<string, unknown> = {}
) {
  return {
    placement: { turn_index: 0, sub_turn_index: null, stage_key: stageKey },
    obj: {
      type,
      stage_key: stageKey,
      stage_order: order,
      iteration: 1,
      ...extra,
    },
  } as any;
}

it("grows the intermediate stage's folded output as deltas stream in", () => {
  // ONE array, mutated in place — exactly what the stream layer does.
  const packets: any[] = [
    fsPacket("flow_stage_start", { label: "Araştırma", node_id: "R" }),
    fsPacket("flow_stage_output_delta", { content: "İlk parça " }),
  ];

  const { rerender } = render(renderMsg(packets));
  fireEvent.click(screen.getByRole("button", { name: /expand timeline/i }));

  expect(screen.getByTestId("stage-output-text").textContent).toContain(
    "İlk parça"
  );
  expect(screen.getByTestId("stage-output-text").textContent).not.toContain(
    "ikinci"
  );

  // A new delta lands on the SAME array; only packetCount changes.
  packets.push(
    fsPacket("flow_stage_output_delta", { content: "ve ikinci parça." })
  );
  rerender(renderMsg(packets));

  expect(screen.getByTestId("stage-output-text").textContent).toContain(
    "İlk parça ve ikinci parça."
  );
});

it("streams the final stage's folded output into the answer bubble live (final node on a loop cycle)", () => {
  // final node sits on an If-Else cycle -> backend folds every iteration as
  // `flow_stage_output_delta` instead of streaming `token`s. No `stop` yet.
  const packets: any[] = [
    stagePacket("flow_stage_start", "Cortex#1", 1, {
      label: "Cortex",
      node_id: "Cortex",
      is_final_stage: true,
    }),
    stagePacket("flow_stage_output_delta", "Cortex#1", 1, {
      content: "Nihai yanıt ",
    }),
  ];

  const { rerender } = render(renderMsg(packets));
  expect(screen.getByTestId("live-final-answer").textContent).toContain(
    "Nihai yanıt"
  );
  // the final stage never renders its own folded "Çıktı" block
  expect(screen.queryByTestId("stage-output-text")).toBeNull();

  packets.push(
    stagePacket("flow_stage_output_delta", "Cortex#1", 1, {
      content: "hazır: 96256 token.",
    })
  );
  rerender(renderMsg(packets));
  expect(screen.getByTestId("live-final-answer").textContent).toContain(
    "Nihai yanıt hazır: 96256 token."
  );

  // run ends: the live block hands off to the `fallbackAnswerText` splice
  // (asserted in flowStageGrouping.test.ts) and stops rendering itself.
  packets.push({
    placement: { turn_index: 0, sub_turn_index: null },
    obj: { type: "stop", stop_reason: "finished" },
  } as any);
  rerender(renderMsg(packets));
  expect(screen.queryByTestId("live-final-answer")).toBeNull();
});
