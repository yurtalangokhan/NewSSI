import type { WireFlowSpec } from "@/components/flow-canvas/types/flow";

/**
 * The graph a brand new flow opens with.
 *
 * Entry and exit nodes are mandatory for publishing (the backend refuses
 * with FLOW_NO_ENTRY / FLOW_NO_EXIT), so seeding them costs the author
 * nothing and removes the empty-canvas cold start. Handle names mirror
 * the component templates exactly: ChatInput emits "message", Chatbot
 * consumes "input" and emits "output", ChatOutput consumes "message"
 * (apps/agent-service/src/domain/flows/templates/core.py).
 */
export function buildSeedFlowSpec(): WireFlowSpec {
  return {
    version: "1.0",
    nodes: [
      {
        id: "chat_input_1",
        type: "ChatInput",
        template_version: 1,
        position: { x: 0, y: 160 },
        values: {},
      },
      {
        id: "agent_1",
        type: "Chatbot",
        template_version: 1,
        position: { x: 320, y: 140 },
        values: {},
      },
      {
        id: "chat_output_1",
        type: "ChatOutput",
        template_version: 1,
        position: { x: 660, y: 160 },
        values: {},
      },
    ],
    edges: [
      {
        id: "edge_input_agent",
        source: "chat_input_1",
        sourceHandle: "message",
        target: "agent_1",
        targetHandle: "input",
      },
      {
        id: "edge_agent_output",
        source: "agent_1",
        sourceHandle: "output",
        target: "chat_output_1",
        targetHandle: "message",
      },
    ],
    viewport: { x: 0, y: 0, zoom: 1 },
  };
}
