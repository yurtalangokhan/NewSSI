import {
  buildStageGroups,
  getActiveStagePreviewStep,
  StageGroup,
  LoopGroup,
} from "./flowStageGrouping";
import { Packet, PacketType } from "@/app/app/services/streamingModels";
import { createInitialState, processPackets } from "./packetProcessor";
import {
  transformPacketGroups,
  groupStepsByTurn,
  TurnGroup,
} from "../transformers";

function p(
  type: string,
  placement: Record<string, unknown> = {},
  obj: Record<string, unknown> = {}
): Packet {
  return {
    placement: {
      turn_index: 0,
      tab_index: 0,
      sub_turn_index: null,
      ...placement,
    },
    obj: { type, ...obj },
  } as unknown as Packet;
}

function stageStart(key: string, extra: Record<string, unknown> = {}) {
  const order = (extra.stage_order as number) ?? 1;
  const iteration = (extra.iteration as number) ?? 1;
  return p(
    "flow_stage_start",
    { stage_key: key, stage_order: order, iteration },
    {
      stage_key: key,
      node_id: key.split("#")[0],
      stage_order: order,
      iteration,
      ...extra,
    }
  );
}

function stageEnd(key: string, extra: Record<string, unknown> = {}) {
  return p(
    "flow_stage_end",
    { stage_key: key },
    { stage_key: key, status: "done", ...extra }
  );
}

function turnGroupsOf(packets: Packet[]): TurnGroup[] {
  let st = createInitialState(1);
  st = processPackets(st, packets);
  return groupStepsByTurn(transformPacketGroups(st.toolGroups));
}

function reasoningStep(stageKey: string, turn: number, text: string): Packet[] {
  return [
    p(PacketType.REASONING_START, { stage_key: stageKey, turn_index: turn }),
    p(
      PacketType.REASONING_DELTA,
      { stage_key: stageKey, turn_index: turn },
      { reasoning: text }
    ),
  ];
}

describe("buildStageGroups", () => {
  it("no sections and turn groups untouched for an agent with no flow_stage_*", () => {
    const packets = [...reasoningStep("", 0, "hi")];
    const tg = turnGroupsOf(packets);
    const r = buildStageGroups(tg, packets);
    expect(r.sections).toEqual([]);
    expect(r.inlineTurnGroups).toBe(tg);
    expect(r.finalStageKey).toBeNull();
  });

  it("folds a non-final stage's steps into a numbered section", () => {
    const packets = [
      stageStart("R#1", { stage_order: 1, label: "Araştırma" }),
      ...reasoningStep("R#1", 0, "thinking"),
      p(
        "flow_stage_output_delta",
        { stage_key: "R#1" },
        { stage_key: "R#1", content: "prep" }
      ),
      stageEnd("R#1", { status: "done", duration_ms: 1200 }),
      stageStart("A#1", {
        stage_order: 2,
        is_final_stage: true,
        label: "Analiz",
      }),
      ...reasoningStep("A#1", 1, "final thinking"),
      p(PacketType.MESSAGE_START, { turn_index: 2 }, { content: "" }),
      p(PacketType.MESSAGE_DELTA, { turn_index: 2 }, { content: "THE ANSWER" }),
      stageEnd("A#1"),
    ];
    const r = buildStageGroups(turnGroupsOf(packets), packets);
    // every stage is a section; the final one carries no folded "Çıktı"
    expect(r.sections.map((s) => (s as StageGroup).stageKey)).toEqual([
      "R#1",
      "A#1",
    ]);
    const research = r.sections[0] as StageGroup;
    expect([
      research.label,
      research.status,
      research.durationMs,
      research.outputText,
    ]).toEqual(["Araştırma", "done", 1200, "prep"]);
    expect(research.turnGroups.length).toBeGreaterThan(0);
    const answer = r.sections[1] as StageGroup;
    expect(answer.outputText).toBe("");
    expect(answer.turnGroups.length).toBeGreaterThan(0);
  });

  it("flattens a stage's steps so nothing renders as parallel tabs", () => {
    const packets = [
      stageStart("R#1", { stage_order: 1, label: "R" }),
      p(
        PacketType.REASONING_DELTA,
        { stage_key: "R#1", turn_index: 0 },
        { reasoning: "hmm" }
      ),
      p(
        PacketType.SEARCH_TOOL_START,
        { stage_key: "R#1", turn_index: 0 },
        { tool_name: "web_search" }
      ),
      p(
        PacketType.SEARCH_TOOL_START,
        { stage_key: "R#1", turn_index: 0 },
        { tool_name: "web_search" }
      ),
      stageEnd("R#1"),
    ];
    const r = buildStageGroups(turnGroupsOf(packets), packets);
    const s = r.sections[0] as StageGroup;
    expect(s.turnGroups.every((g) => g.isParallel === false)).toBe(true);
    expect(s.turnGroups.every((g) => g.steps.length === 1)).toBe(true);
  });

  it("folds repeated node iterations into a LoopGroup", () => {
    const packets = [1, 2, 3].flatMap((i) => [
      stageStart(`A#${i}`, { stage_order: i, iteration: i, label: "Analiz" }),
      ...reasoningStep(`A#${i}`, i - 1, `iter ${i}`),
      stageEnd(`A#${i}`, { duration_ms: 100 }),
    ]);
    const r = buildStageGroups(turnGroupsOf(packets), packets);
    expect(r.sections).toHaveLength(1);
    const loop = r.sections[0] as LoopGroup;
    expect([
      loop.kind,
      loop.iterationCount,
      loop.iterations.length,
      loop.durationMs,
    ]).toEqual(["loop", 3, 3, 300]);
  });

  it("does not create a LoopGroup when every iteration is 1", () => {
    const packets = [
      stageStart("A#1", { stage_order: 1, label: "A" }),
      stageEnd("A#1"),
      stageStart("B#1", { stage_order: 2, label: "B" }),
      stageEnd("B#1"),
    ];
    const r = buildStageGroups(turnGroupsOf(packets), packets);
    expect(r.sections.every((s) => s.kind === "stage")).toBe(true);
    expect(r.sections).toHaveLength(2);
  });

  it("marks a stage running when it has a start but no end", () => {
    const packets = [stageStart("A#1", { stage_order: 1, label: "A" })];
    const r = buildStageGroups(turnGroupsOf(packets), packets);
    expect((r.sections[0] as StageGroup).status).toBe("running");
  });

  it("orders sections by stage_order", () => {
    const packets = [
      stageStart("B#1", { stage_order: 2, label: "B" }),
      stageEnd("B#1"),
      stageStart("A#1", { stage_order: 1, label: "A" }),
      stageEnd("A#1"),
    ];
    const r = buildStageGroups(turnGroupsOf(packets), packets);
    expect(r.sections.map((s) => (s as StageGroup).label)).toEqual(["A", "B"]);
  });

  it("promotes the last stage's folded text to fallbackAnswerText only after the run ends with no real answer", () => {
    const base = [
      stageStart("R#1", { stage_order: 1, label: "R" }),
      p(
        "flow_stage_output_delta",
        { stage_key: "R#1" },
        { stage_key: "R#1", content: "draft" }
      ),
      stageEnd("R#1"),
    ];
    expect(buildStageGroups([], base).fallbackAnswerText).toBe("");

    const ended = [
      ...base,
      p(PacketType.STOP, {}, { stop_reason: "finished" }),
    ];
    const r = buildStageGroups(turnGroupsOf(ended), ended);
    expect(r.fallbackAnswerText).toBe("draft");
    expect((r.sections[0] as StageGroup).outputText).toBe("");

    const endedWithAnswer = [
      ...base,
      p(PacketType.MESSAGE_DELTA, {}, { content: "real" }),
      p(PacketType.STOP, {}, { stop_reason: "finished" }),
    ];
    expect(buildStageGroups([], endedWithAnswer).fallbackAnswerText).toBe("");
  });

  it("streams the running final stage's folded text via liveFinalAnswerText, then hands off to fallbackAnswerText at stop", () => {
    const running = [
      stageStart("Research#1", { stage_order: 1, label: "Research" }),
      p(
        "flow_stage_output_delta",
        { stage_key: "Research#1" },
        { stage_key: "Research#1", content: "brief" }
      ),
      stageEnd("Research#1"),
      stageStart("Cortex#1", {
        stage_order: 2,
        label: "Cortex",
        is_final_stage: true,
      }),
      p(
        "flow_stage_output_delta",
        { stage_key: "Cortex#1" },
        { stage_key: "Cortex#1", content: "final answer " }
      ),
    ];
    let r = buildStageGroups([], running);
    // mid-run: promoted live, not as the end-of-run fallback
    expect(r.liveFinalAnswerText).toBe("final answer ");
    expect(r.fallbackAnswerText).toBe("");
    // intermediate stage still folds normally
    expect((r.sections[0] as StageGroup).outputText).toBe("brief");
    // the final stage never renders its own folded block
    expect((r.sections[1] as StageGroup).outputText).toBe("");

    // more of the final stage streams in
    const more = [
      ...running,
      p(
        "flow_stage_output_delta",
        { stage_key: "Cortex#1" },
        { stage_key: "Cortex#1", content: "= 96256" }
      ),
    ];
    expect(buildStageGroups([], more).liveFinalAnswerText).toBe(
      "final answer = 96256"
    );

    // run ends: live promotion stops, fallback takes over with the same text
    const ended = [
      ...more,
      p(PacketType.STOP, {}, { stop_reason: "finished" }),
    ];
    r = buildStageGroups([], ended);
    expect(r.liveFinalAnswerText).toBe("");
    expect(r.fallbackAnswerText).toBe("final answer = 96256");
  });

  it("does not promote a non-final running stage's folded text", () => {
    const running = [
      stageStart("Analysis#1", { stage_order: 1, label: "Analysis" }),
      p(
        "flow_stage_output_delta",
        { stage_key: "Analysis#1" },
        { stage_key: "Analysis#1", content: "calc" }
      ),
    ];
    expect(buildStageGroups([], running).liveFinalAnswerText).toBe("");
  });
});

describe("getActiveStagePreviewStep", () => {
  it("returns undefined when there are no sections", () => {
    expect(getActiveStagePreviewStep([])).toBeUndefined();
  });

  it("returns the running stage's last step while a later stage has not started", () => {
    const packets = [
      stageStart("R#1", { stage_order: 1, label: "Research" }),
      ...reasoningStep("R#1", 0, "first thought"),
      stageEnd("R#1"),
      stageStart("A#1", { stage_order: 2, label: "Analysis" }),
      ...reasoningStep("A#1", 1, "second thought"),
      // no stageEnd for A#1 -> it is the running stage
    ];
    const { sections } = buildStageGroups(turnGroupsOf(packets), packets);
    const step = getActiveStagePreviewStep(sections);
    expect(step).toBeDefined();
    // it comes from the running stage (A#1), not the finished one
    const inRunning = (sections[1] as StageGroup).turnGroups
      .flatMap((tg) => tg.steps)
      .some((s) => s.key === step!.key);
    expect(inRunning).toBe(true);
  });

  it("falls back to the last stage overall when none is marked running", () => {
    const packets = [
      stageStart("R#1", { stage_order: 1, label: "Research" }),
      ...reasoningStep("R#1", 0, "only thought"),
      stageEnd("R#1"),
    ];
    const { sections } = buildStageGroups(turnGroupsOf(packets), packets);
    expect(getActiveStagePreviewStep(sections)).toBeDefined();
  });

  it("returns undefined when the running stage has produced no step yet", () => {
    const packets = [stageStart("R#1", { stage_order: 1, label: "Research" })];
    const { sections } = buildStageGroups(turnGroupsOf(packets), packets);
    expect(getActiveStagePreviewStep(sections)).toBeUndefined();
  });

  it("reaches into a loop's iterations for the running stage", () => {
    const packets = [1, 2].flatMap((i) => [
      stageStart(`A#${i}`, { stage_order: i, iteration: i, label: "Analiz" }),
      ...reasoningStep(`A#${i}`, i - 1, `iter ${i}`),
      ...(i === 1 ? [stageEnd(`A#${i}`)] : []),
    ]);
    const { sections } = buildStageGroups(turnGroupsOf(packets), packets);
    expect(sections[0]?.kind).toBe("loop");
    expect(getActiveStagePreviewStep(sections)).toBeDefined();
  });
});
