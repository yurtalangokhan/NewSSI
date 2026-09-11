import { Packet, PacketType } from "@/app/app/services/streamingModels";
import { TransformedStep, TurnGroup } from "../transformers";

/**
 * One numbered stage of a FlowAgent run — a canvas agent/model node's
 * execution, or one loop iteration of it. Holds the timeline steps
 * (`turnGroups`, already produced by the shared packet pipeline) that belong
 * to it, plus its own folded message text (`outputText`) for intermediate
 * stages.
 */
export interface StageGroup {
  kind: "stage";
  stageKey: string;
  nodeId: string;
  label: string;
  order: number;
  iteration: number;
  status: "running" | "done" | "error" | "cancelled";
  durationMs: number | null;
  isFinal?: boolean;
  outputText: string;
  turnGroups: TurnGroup[];
}

/** A loop whose body ran more than once — its per-iteration stage groups
 *  nest under one collapsible header. */
export interface LoopGroup {
  kind: "loop";
  label: string;
  iterationCount: number;
  durationMs: number | null;
  iterations: StageGroup[][];
}

export type TimelineSection = StageGroup | LoopGroup;

export interface StageGroupingResult {
  /** Numbered stage / loop sections, in run order. */
  sections: TimelineSection[];
  /** Timeline steps that are NOT folded into a stage section — the final
   *  (answer) stage's steps and any un-attributed steps. Rendered inline in
   *  the AgentTimeline as before. */
  inlineTurnGroups: TurnGroup[];
  /** stage_key of the final stage, if the run marked one. */
  finalStageKey: string | null;
  /** The last stage's folded text, surfaced only when the run ended with no
   *  real answer packet, so `AgentMessage` can still render an answer. */
  fallbackAnswerText: string;
  /** The final stage's folded text WHILE the run is still going — for a flow
   *  whose final node sits on a loop cycle, the backend can't know which
   *  iteration is last so it folds every one instead of streaming tokens.
   *  `AgentMessage` promotes this into the answer bubble so the final answer
   *  streams live (and re-streams if the loop runs again) instead of only
   *  appearing whole at `stop` via `fallbackAnswerText`. */
  liveFinalAnswerText: string;
}

interface StageMeta {
  stageKey: string;
  nodeId: string;
  label: string;
  order: number;
  iteration: number;
  status: StageGroup["status"];
  durationMs: number | null;
  isFinal: boolean;
  outputText: string;
}

const ANSWER_TYPES = new Set([
  "message_start",
  "message_delta",
  "message_end",
  "token",
]);

function stageKeyOfTurn(tg: TurnGroup): string | undefined {
  for (const step of tg.steps) {
    for (const pk of step.packets) {
      const k = pk.placement?.stage_key;
      if (k) return k;
    }
  }
  return undefined;
}

/** Extract per-stage metadata + folded output text from the raw packet list. */
function extractStageMeta(packets: Packet[]): {
  metaByKey: Map<string, StageMeta>;
  orderedKeys: string[];
  finalStageKey: string | null;
} {
  const metaByKey = new Map<string, StageMeta>();
  const orderedKeys: string[] = [];
  let finalStageKey: string | null = null;

  const ensure = (key: string, placement?: Packet["placement"]): StageMeta => {
    let m = metaByKey.get(key);
    if (!m) {
      m = {
        stageKey: key,
        nodeId: key.split("#")[0] ?? key,
        label: key,
        order: placement?.stage_order ?? Number.MAX_SAFE_INTEGER,
        iteration: placement?.iteration ?? 1,
        status: "running",
        durationMs: null,
        isFinal: false,
        outputText: "",
      };
      metaByKey.set(key, m);
      orderedKeys.push(key);
    }
    return m;
  };

  for (const packet of packets) {
    const type = String(packet.obj?.type ?? "");
    const o = packet.obj as unknown as Record<string, unknown>;
    const key = (o.stage_key as string) || packet.placement?.stage_key;
    if (!key) continue;

    if (type === PacketType.FLOW_STAGE_START) {
      const m = ensure(key, packet.placement);
      if (typeof o.label === "string" && o.label) m.label = o.label;
      if (typeof o.node_id === "string" && o.node_id) m.nodeId = o.node_id;
      if (typeof o.stage_order === "number") m.order = o.stage_order;
      if (typeof o.iteration === "number") m.iteration = o.iteration;
      m.isFinal = Boolean(o.is_final_stage ?? packet.placement?.is_final_stage);
      if (m.isFinal) finalStageKey = key;
    } else if (type === PacketType.FLOW_STAGE_END) {
      const m = ensure(key, packet.placement);
      const st = String(o.status ?? "done");
      m.status =
        st === "error" || st === "cancelled" || st === "running"
          ? (st as StageGroup["status"])
          : "done";
      if (typeof o.duration_ms === "number") m.durationMs = o.duration_ms;
    } else if (type === PacketType.FLOW_STAGE_OUTPUT_DELTA) {
      const m = ensure(key, packet.placement);
      if (typeof o.content === "string") m.outputText += o.content;
    }
  }

  return { metaByKey, orderedKeys, finalStageKey };
}

/** Flatten a stage's turn groups so no two steps share a turn — a folded
 *  stage never renders "Thinking"/"Tool" parallel tabs. */
function flattenTurnGroups(turnGroups: TurnGroup[]): TurnGroup[] {
  const out: TurnGroup[] = [];
  let t = 0;
  for (const tg of turnGroups) {
    for (const step of tg.steps) {
      out.push({
        turnIndex: t,
        isParallel: false,
        steps: [{ ...step, turnIndex: t, tabIndex: 0 }],
      });
      t += 1;
    }
  }
  return out;
}

/**
 * Split the shared pipeline's `turnGroups` into numbered per-stage sections
 * plus the steps that stay inline. Pure. Returns empty `sections` and the
 * turn groups untouched for any agent that never emits `flow_stage_*`.
 */
export function buildStageGroups(
  turnGroups: TurnGroup[],
  packets: Packet[]
): StageGroupingResult {
  const { metaByKey, orderedKeys, finalStageKey } = extractStageMeta(packets);

  if (metaByKey.size === 0) {
    return {
      sections: [],
      inlineTurnGroups: turnGroups,
      finalStageKey: null,
      fallbackAnswerText: "",
      liveFinalAnswerText: "",
    };
  }

  // Every stage — the final one included — becomes a numbered section so its
  // reasoning + tool steps are visible. The final stage's visible ANSWER text
  // rides separate `message_start`/`token` packets (display groups → the
  // bubble), not a turn group, so nothing is duplicated.
  const byStage = new Map<string, TurnGroup[]>();
  const inlineTurnGroups: TurnGroup[] = [];
  for (const tg of turnGroups) {
    const key = stageKeyOfTurn(tg);
    if (key && metaByKey.has(key)) {
      const list = byStage.get(key) ?? [];
      list.push(tg);
      byStage.set(key, list);
    } else {
      inlineTurnGroups.push(tg);
    }
  }

  const metas = orderedKeys
    .map((k) => metaByKey.get(k)!)
    .sort((a, b) => a.order - b.order);

  const stageGroups: StageGroup[] = metas.map((m) => ({
    kind: "stage" as const,
    stageKey: m.stageKey,
    nodeId: m.nodeId,
    label: m.label && m.label !== m.stageKey ? m.label : m.nodeId || m.stageKey,
    order: m.order,
    iteration: m.iteration,
    status: m.status,
    durationMs: m.durationMs,
    isFinal: m.isFinal,
    // the final stage's text is the answer bubble, never a folded "Çıktı" block
    outputText: m.isFinal ? "" : m.outputText,
    turnGroups: flattenTurnGroups(byStage.get(m.stageKey) ?? []),
  }));

  // fallback answer: the run ended with no real answer packet — promote the
  // last stage's folded text so the bubble still renders and the message
  // completes.
  let hasRealAnswer = false;
  let runEnded = false;
  for (const p of packets) {
    const t = String(p.obj?.type ?? "");
    if (ANSWER_TYPES.has(t)) hasRealAnswer = true;
    if (t === "stop") runEnded = true;
  }
  const lastMeta = metas[metas.length - 1];
  const fallbackAnswerText =
    runEnded && !hasRealAnswer && lastMeta ? lastMeta.outputText.trim() : "";
  if (fallbackAnswerText && lastMeta) {
    const last = stageGroups[stageGroups.length - 1];
    if (last && last.stageKey === lastMeta.stageKey) last.outputText = "";
  }

  // Live promotion: the final node folded its output (it sits on a loop cycle,
  // so the backend streamed `flow_stage_output_delta` instead of `token`).
  // Surface the current final-stage iteration's text so the answer bubble
  // streams it live; a new iteration replaces it (its meta starts empty).
  const liveFinalAnswerText =
    !runEnded && !hasRealAnswer && lastMeta?.isFinal ? lastMeta.outputText : "";

  return {
    sections: collapseLoops(stageGroups),
    inlineTurnGroups,
    finalStageKey,
    fallbackAnswerText,
    liveFinalAnswerText,
  };
}

/** Fold stage groups whose node ran more than once into one LoopGroup. */
function collapseLoops(stageGroups: StageGroup[]): TimelineSection[] {
  const maxIterByNode = new Map<string, number>();
  for (const s of stageGroups) {
    maxIterByNode.set(
      s.nodeId,
      Math.max(maxIterByNode.get(s.nodeId) ?? 1, s.iteration)
    );
  }
  const isLoopStage = (s: StageGroup) =>
    (maxIterByNode.get(s.nodeId) ?? 1) >= 2;
  if (!stageGroups.some(isLoopStage)) return [...stageGroups];

  const loopMembers = stageGroups.filter(isLoopStage);
  const iterationCount = loopMembers.reduce(
    (m, s) => Math.max(m, s.iteration),
    1
  );
  const iterations: StageGroup[][] = [];
  for (let k = 1; k <= iterationCount; k++) {
    iterations.push(loopMembers.filter((s) => s.iteration === k));
  }
  const durationMs = loopMembers.every((s) => s.durationMs == null)
    ? null
    : loopMembers.reduce((sum, s) => sum + (s.durationMs ?? 0), 0);

  const loop: LoopGroup = {
    kind: "loop",
    // Base node label only — the rendering layer appends a translated
    // "loop" suffix (this module is pure, no i18n).
    label: mostCommon(loopMembers.map((s) => s.label)),
    iterationCount,
    durationMs,
    iterations,
  };

  const out: TimelineSection[] = [];
  let inserted = false;
  for (const s of stageGroups) {
    if (isLoopStage(s)) {
      if (!inserted) {
        out.push(loop);
        inserted = true;
      }
    } else {
      out.push(s);
    }
  }
  return out;
}

function mostCommon(values: string[]): string {
  const counts = new Map<string, number>();
  for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1);
  let best = values[0] ?? "";
  let bestN = 0;
  Array.from(counts.entries()).forEach(([v, n]) => {
    if (n > bestN) {
      best = v;
      bestN = n;
    }
  });
  return best;
}

/**
 * The single timeline step to peek under the header while a flow run streams
 * and the card is still collapsed — the last step of the stage that is
 * currently running (or, if none is marked running, the last stage overall).
 * This is what restores the brief "thinking" preview non-flow agents show in
 * their collapsed state; a flow run folds every step into a numbered section,
 * so without this the collapsed card would be empty until the user expands it.
 * `undefined` when no stage has produced a step yet.
 */
export function getActiveStagePreviewStep(
  sections: TimelineSection[]
): TransformedStep | undefined {
  const stages: StageGroup[] = [];
  for (const sec of sections) {
    if (sec.kind === "stage") stages.push(sec);
    else for (const iteration of sec.iterations) stages.push(...iteration);
  }

  const target =
    [...stages].reverse().find((s) => s.status === "running") ??
    stages[stages.length - 1];
  if (!target) return undefined;

  for (let i = target.turnGroups.length - 1; i >= 0; i--) {
    const steps = target.turnGroups[i]?.steps;
    if (steps && steps.length > 0) return steps[steps.length - 1];
  }
  return undefined;
}
