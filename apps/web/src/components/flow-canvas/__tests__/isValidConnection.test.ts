/**
 * Tests for isValidConnection.ts.
 *
 * Ported from Langflow (MIT) — src/frontend/src/utils/reactflowUtils.ts
 * (isValidConnection), concept only: Langflow's version reasons about its
 * own dataType/inputTypes/output_types handle-descriptor shape and
 * additionally implements loop-input cycle detection. Neither applies to
 * us — type compatibility is Task 22's own `handleTypes.ts`
 * (backend-mirrored), and general-graph cycle detection is the backend
 * validator's job at save/publish time (FLOW_ILLEGAL_CYCLE, P1 Task 3),
 * with the sanctioned exception routed through a Loop node (R2). Porting a
 * second, client-side cycle check here would duplicate that logic outside
 * this task's anti-drift guarantee and was deliberately not done — see
 * task-22-report.md.
 *
 * Handle-type resolution is injected (a plain lookup function) rather than
 * fetched from the component registry here, keeping this module pure and
 * independently testable; Task 24 wires the real lookup from the
 * registry (Task 25/26).
 *
 * Brief: .tmp/flow-canvas-task-22-brief.md
 */

import type { CanvasEdge, PortType } from "../types/flow";
import { isValidConnection } from "../utils/isValidConnection";

function edge(
  id: string,
  source: string,
  target: string,
  sourceHandle: string,
  targetHandle: string
): CanvasEdge {
  return { id, source, target, sourceHandle, targetHandle };
}

// A minimal handle registry for the tests: node "in" outputs Message on
// "message"; node "agent" accepts Message on "input", outputs Message on
// "output"; node "out" accepts Message on "message".
function lookup(
  _nodeId: string,
  handleName: string,
  _direction: "source" | "target"
): PortType[] | null {
  if (
    handleName === "message" ||
    handleName === "input" ||
    handleName === "output"
  ) {
    return ["Message"];
  }
  if (handleName === "trigger") return ["Trigger"];
  if (handleName === "tools") return ["Tools"];
  if (handleName === "model") return ["Model"];
  return null;
}

describe("isValidConnection", () => {
  it("22.7 — rejects a self-connection", () => {
    const ok = isValidConnection(
      {
        source: "agent",
        target: "agent",
        sourceHandle: "output",
        targetHandle: "input",
      },
      [],
      lookup
    );
    expect(ok).toBe(false);
  });

  it("22.8 — rejects a duplicate edge (same source/handle -> target/handle)", () => {
    const existing = [edge("e1", "in", "agent", "message", "input")];

    const ok = isValidConnection(
      {
        source: "in",
        target: "agent",
        sourceHandle: "message",
        targetHandle: "input",
      },
      existing,
      lookup
    );

    expect(ok).toBe(false);
  });

  it("22.9 — rejects a second edge into an already-occupied single-value target handle", () => {
    const existing = [edge("e1", "in", "agent", "message", "input")];

    const ok = isValidConnection(
      {
        source: "other-in",
        target: "agent",
        sourceHandle: "message",
        targetHandle: "input",
      },
      existing,
      lookup
    );

    expect(ok).toBe(false);
  });

  it("accepts a second edge into a Tools-type target handle (an agent takes many tools)", () => {
    const existing = [edge("e1", "tool-a", "agent", "tools", "tools")];

    const ok = isValidConnection(
      {
        source: "tool-b",
        target: "agent",
        sourceHandle: "tools",
        targetHandle: "tools",
      },
      existing,
      lookup
    );

    expect(ok).toBe(true);
  });

  it("still rejects a second edge into an already-occupied single-value target handle like model", () => {
    const existing = [edge("e1", "model-a", "agent", "model", "model")];

    const ok = isValidConnection(
      {
        source: "model-b",
        target: "agent",
        sourceHandle: "model",
        targetHandle: "model",
      },
      existing,
      lookup
    );

    expect(ok).toBe(false);
  });

  it("accepts a legal, non-duplicate, non-occupied connection", () => {
    const ok = isValidConnection(
      {
        source: "in",
        target: "agent",
        sourceHandle: "message",
        targetHandle: "input",
      },
      [],
      lookup
    );

    expect(ok).toBe(true);
  });

  it("rejects an incompatible type pair even with free handles", () => {
    const ok = isValidConnection(
      {
        source: "in",
        target: "agent",
        sourceHandle: "trigger",
        targetHandle: "input",
      },
      [],
      lookup
    );

    expect(ok).toBe(false);
  });

  it("rejects a connection whose handle cannot be resolved", () => {
    const ok = isValidConnection(
      {
        source: "in",
        target: "agent",
        sourceHandle: "unknown-handle",
        targetHandle: "input",
      },
      [],
      lookup
    );

    expect(ok).toBe(false);
  });

  it("rejects a connection missing any endpoint field", () => {
    expect(
      isValidConnection(
        {
          source: "in",
          target: "agent",
          sourceHandle: null,
          targetHandle: "input",
        },
        [],
        lookup
      )
    ).toBe(false);
  });
});
