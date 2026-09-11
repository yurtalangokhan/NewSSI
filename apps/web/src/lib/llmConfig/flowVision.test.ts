import { LLMProviderDescriptor, ModelConfiguration } from "@/interfaces/llm";
import { collectFlowModelRefs, flowModelsSupportImageInput } from "./utils";

const model = (
  name: string,
  supports_image_input: boolean
): ModelConfiguration => ({
  name,
  is_visible: true,
  max_input_tokens: null,
  supports_image_input,
  supports_reasoning: false,
});

const providers: LLMProviderDescriptor[] = [
  {
    id: 1,
    name: "OpenAI",
    provider: "openai",
    provider_display_name: "OpenAI",
    model_configurations: [model("gpt-4o", true), model("o1-mini", false)],
  },
  {
    id: 2,
    name: "Ollama",
    provider: "ollama",
    provider_display_name: "Ollama",
    model_configurations: [model("llava", true), model("llama3", false)],
  },
];

const node = (type: string, values?: Record<string, unknown>) => ({
  type,
  values,
});

describe("flowModelsSupportImageInput", () => {
  it("returns true when every flow model supports image input", () => {
    const spec = {
      nodes: [node("LLMModel", { provider: "OpenAI", model: "gpt-4o" })],
    };
    expect(flowModelsSupportImageInput(providers, spec, "gpt-4o")).toBe(true);
  });

  it("returns false when at least one flow model lacks vision support", () => {
    const spec = {
      nodes: [
        node("LLMModel", { provider: "OpenAI", model: "gpt-4o" }),
        node("LLMModel", { provider: "OpenAI", model: "o1-mini" }),
      ],
    };
    expect(flowModelsSupportImageInput(providers, spec, "gpt-4o")).toBe(false);
  });

  it("evaluates a node with no explicit model against the system default", () => {
    const spec = { nodes: [node("LLMModel", { provider: "OpenAI" })] };
    expect(flowModelsSupportImageInput(providers, spec, "o1-mini")).toBe(false);
    expect(flowModelsSupportImageInput(providers, spec, "gpt-4o")).toBe(true);
  });

  it("includes the system default when the flow has multiple model nodes", () => {
    const spec = {
      nodes: [
        node("LLMModel", { provider: "OpenAI", model: "gpt-4o" }),
        node("OllamaModel", { model: "llava" }),
      ],
    };
    expect(flowModelsSupportImageInput(providers, spec, "gpt-4o")).toBe(true);
    expect(flowModelsSupportImageInput(providers, spec, "o1-mini")).toBe(false);
  });

  it("resolves OllamaModel nodes by model name", () => {
    expect(
      flowModelsSupportImageInput(
        providers,
        { nodes: [node("OllamaModel", { model: "llava" })] },
        "gpt-4o"
      )
    ).toBe(true);
    expect(
      flowModelsSupportImageInput(
        providers,
        { nodes: [node("OllamaModel", { model: "llama3" })] },
        "gpt-4o"
      )
    ).toBe(false);
  });

  it("ignores non-model nodes", () => {
    const spec = {
      nodes: [
        node("Agent", { name: "Researcher" }),
        node("ChatInput"),
        node("LLMModel", { provider: "OpenAI", model: "gpt-4o" }),
      ],
    };
    expect(flowModelsSupportImageInput(providers, spec, "o1-mini")).toBe(true);
  });

  it("returns false when the flow spec is missing, empty, or has no nodes", () => {
    expect(flowModelsSupportImageInput(providers, null, "gpt-4o")).toBe(false);
    expect(flowModelsSupportImageInput(providers, undefined, "gpt-4o")).toBe(
      false
    );
    expect(
      flowModelsSupportImageInput(providers, { nodes: [] }, "gpt-4o")
    ).toBe(false);
    expect(flowModelsSupportImageInput(providers, {}, "gpt-4o")).toBe(false);
  });

  // A hand-authored / UI-authored LLMModel node stores `values.provider` as the
  // provider *type* ("ollama") or its UUID, never the descriptor display name.
  // The vision gate must still resolve the model instead of failing closed.
  it("resolves a flow node whose provider is the provider type, not its display name", () => {
    const typed: LLMProviderDescriptor[] = [
      {
        id: "11111111-1111-1111-1111-111111111111",
        name: "Ollama 3",
        provider: "ollama",
        provider_display_name: "Ollama 3",
        model_configurations: [model("qwen3.6:27b", true)],
      },
      {
        id: "22222222-2222-2222-2222-222222222222",
        name: "Ollama (Yerel Sağlayıcılar)",
        provider: "ollama",
        provider_display_name: "Ollama (Yerel Sağlayıcılar)",
        model_configurations: [],
      },
    ];
    const spec = {
      nodes: [
        node("LLMModel", {
          model: "qwen3.6:27b",
          provider: "ollama",
          temperature: 0.7,
        }),
      ],
    };
    expect(flowModelsSupportImageInput(typed, spec, "qwen3.5:9b")).toBe(true);
  });

  it("resolves a flow node whose provider is the provider UUID", () => {
    const typed: LLMProviderDescriptor[] = [
      {
        id: "11111111-1111-1111-1111-111111111111",
        name: "Ollama 3",
        provider: "ollama",
        provider_display_name: "Ollama 3",
        model_configurations: [model("qwen3.6:27b", true)],
      },
    ];
    const spec = {
      nodes: [
        node("LLMModel", {
          model: "qwen3.6:27b",
          provider: "11111111-1111-1111-1111-111111111111",
        }),
      ],
    };
    expect(flowModelsSupportImageInput(typed, spec, "qwen3.5:9b")).toBe(true);
  });

  // Multi-model flow whose nodes carry provider *types*: the lenient provider
  // resolution must not let a mixed set through — every reachable model (each
  // node + the system default) still has to support vision.
  it("still requires every model in a multi-node flow to support vision (type hints)", () => {
    const typed: LLMProviderDescriptor[] = [
      {
        id: "11111111-1111-1111-1111-111111111111",
        name: "Ollama 3",
        provider: "ollama",
        provider_display_name: "Ollama 3",
        model_configurations: [
          model("qwen3.6:27b", true),
          model("qwen3.5:9b", false),
        ],
      },
    ];
    const mixed = {
      nodes: [
        node("LLMModel", { model: "qwen3.6:27b", provider: "ollama" }),
        node("OllamaModel", { model: "qwen3.5:9b", provider: "ollama" }),
      ],
    };
    // qwen3.6 has vision, qwen3.5 does not -> blocked.
    expect(flowModelsSupportImageInput(typed, mixed, "qwen3.6:27b")).toBe(
      false
    );

    const allVision = {
      nodes: [
        node("LLMModel", { model: "qwen3.6:27b", provider: "ollama" }),
        node("OllamaModel", { model: "qwen3.6:27b", provider: "ollama" }),
      ],
    };
    // every node supports vision, but the system default (qwen3.5:9b) does not,
    // and a >1-model flow includes the default -> still blocked.
    expect(flowModelsSupportImageInput(typed, allVision, "qwen3.5:9b")).toBe(
      false
    );
    // ...and allowed once the default supports vision too.
    expect(flowModelsSupportImageInput(typed, allVision, "qwen3.6:27b")).toBe(
      true
    );
  });
});

describe("collectFlowModelRefs", () => {
  it("maps an unset model to the default and leaves an unset provider null", () => {
    expect(
      collectFlowModelRefs(
        { nodes: [node("OllamaModel", { model: "llava" })] },
        "gpt-4o"
      )
    ).toEqual([{ model: "llava", provider: null }]);
  });

  it("does not add the default for a single-model flow", () => {
    const refs = collectFlowModelRefs(
      { nodes: [node("LLMModel", { provider: "OpenAI", model: "gpt-4o" })] },
      "o1-mini"
    );
    expect(refs).toEqual([{ model: "gpt-4o", provider: "OpenAI" }]);
  });

  it("adds the default when there are zero or many model nodes", () => {
    expect(collectFlowModelRefs({ nodes: [node("Agent")] }, "gpt-4o")).toEqual([
      { model: "gpt-4o", provider: null },
    ]);
    expect(
      collectFlowModelRefs(
        {
          nodes: [
            node("LLMModel", { provider: "OpenAI", model: "gpt-4o" }),
            node("OllamaModel", { model: "llava" }),
          ],
        },
        "gpt-4o"
      )
    ).toEqual([
      { model: "gpt-4o", provider: "OpenAI" },
      { model: "llava", provider: null },
      { model: "gpt-4o", provider: null },
    ]);
  });
});
