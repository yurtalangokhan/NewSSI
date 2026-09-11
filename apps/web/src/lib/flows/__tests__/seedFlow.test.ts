import { buildSeedFlowSpec } from "@/lib/flows/seedFlow";

describe("buildSeedFlowSpec", () => {
  it("wires ChatInput -> Chatbot -> ChatOutput", () => {
    const spec = buildSeedFlowSpec();

    expect(spec.version).toBe("1.0");
    expect(spec.nodes.map((n) => n.type)).toEqual([
      "ChatInput",
      "Chatbot",
      "ChatOutput",
    ]);

    const [inputEdge, outputEdge] = spec.edges;
    expect(inputEdge).toMatchObject({
      source: "chat_input_1",
      sourceHandle: "message",
      target: "agent_1",
      targetHandle: "input",
    });
    expect(outputEdge).toMatchObject({
      source: "agent_1",
      sourceHandle: "output",
      target: "chat_output_1",
      targetHandle: "message",
    });
  });
});
