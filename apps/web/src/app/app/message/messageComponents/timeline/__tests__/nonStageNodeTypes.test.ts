/**
 * The timeline's "which node types never become a numbered stage" answer.
 *
 * The compiler owns the real list (`PASSTHROUGH_NODE_TYPES` in
 * `agents/graphs/flow_builder.py`, re-exported from `agents.graphs`), and the
 * server already filters live runs with it. This copy is only reached for
 * legacy packets that arrive without stage attribution — but it had drifted to
 * four entries while the compiler grew to thirteen, so every control-flow node
 * added since (While, SetVariable, Smart Router, Human Input, If-Else...)
 * leaked through as an empty stage.
 *
 * If this test fails after a node type is added, add it in both places.
 */
import { NON_STAGE_NODE_TYPES } from "@/app/app/message/messageComponents/timeline/graphStageParsing";

// Mirrors PASSTHROUGH_NODE_TYPES in apps/agent-service/src/agents/graphs/flow_builder.py
const COMPILER_PASSTHROUGH_NODE_TYPES = [
  "ChatInput",
  "ChatOutput",
  "ConditionalRouter",
  "FileInput",
  "HumanInput",
  "Loop",
  "Merge",
  "PromptTemplate",
  "Router",
  "SetVariable",
  "SmartRouter",
  "TextInput",
  "While",
];

describe("NON_STAGE_NODE_TYPES", () => {
  it("matches the compiler's passthrough set", () => {
    // Array.from, not spread: ts-jest compiles this project without
    // downlevelIteration, where spreading a Set silently yields [].
    expect(Array.from(NON_STAGE_NODE_TYPES).sort()).toEqual(
      COMPILER_PASSTHROUGH_NODE_TYPES.slice().sort()
    );
  });

  it("covers the control-flow nodes the old inline list missed", () => {
    for (const type of [
      "While",
      "SetVariable",
      "SmartRouter",
      "HumanInput",
      "ConditionalRouter",
    ]) {
      expect(NON_STAGE_NODE_TYPES.has(type)).toBe(true);
    }
  });
});
