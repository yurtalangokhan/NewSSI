import {
  buildLlmOptions,
  groupLlmOptions,
  isLlmOptionAvailableForSelection,
} from "./LLMPopover";
import { LLMOption } from "./interfaces";
import { LLMProviderDescriptor } from "@/interfaces/llm";
import { makeProvider } from "@tests/setup/llmProviderTestUtils";

describe("LLMPopover helpers", () => {
  test("deduplicates identical provider+model combinations across provider entries", () => {
    const providers: LLMProviderDescriptor[] = [
      makeProvider({
        id: 1,
        name: "OpenAI A",
        provider: "openai",
        model_configurations: [
          {
            name: "shared-model",
            is_visible: true,
            max_input_tokens: null,
            supports_image_input: false,
            supports_reasoning: false,
          },
        ],
      }),
      makeProvider({
        id: 2,
        name: "OpenAI B",
        provider: "openai",
        model_configurations: [
          {
            name: "shared-model",
            is_visible: true,
            max_input_tokens: null,
            supports_image_input: false,
            supports_reasoning: false,
          },
        ],
      }),
      makeProvider({
        id: 3,
        name: "Anthropic A",
        provider: "anthropic",
        model_configurations: [
          {
            name: "shared-model",
            is_visible: true,
            max_input_tokens: null,
            supports_image_input: false,
            supports_reasoning: false,
          },
        ],
      }),
    ];

    const options = buildLlmOptions(providers);
    const sharedModelOptions = options.filter(
      (o) => o.modelName === "shared-model"
    );

    expect(sharedModelOptions).toHaveLength(3);
    expect(sharedModelOptions.map((o) => o.name).sort()).toEqual([
      "Anthropic A",
      "OpenAI A",
      "OpenAI B",
    ]);
  });

  test("includes currently selected hidden model in options", () => {
    const providers: LLMProviderDescriptor[] = [
      makeProvider({
        name: "OpenAI A",
        provider: "openai",
        model_configurations: [
          {
            name: "hidden-selected-model",
            is_visible: false,
            max_input_tokens: null,
            supports_image_input: false,
            supports_reasoning: false,
          },
        ],
      }),
    ];

    const options = buildLlmOptions(providers, "hidden-selected-model");
    expect(options.map((o) => o.modelName)).toContain("hidden-selected-model");
    expect(options[0]?.isAvailable).toBe(false);
    expect(isLlmOptionAvailableForSelection(options[0]!)).toBe(false);
  });

  test("groups aggregator options by provider/vendor and sorts by display name", () => {
    const options: LLMOption[] = [
      {
        name: "Bedrock Provider",
        provider: "bedrock",
        providerDisplayName: "Amazon Bedrock",
        modelName: "claude-3-5-sonnet",
        displayName: "Claude 3.5 Sonnet",
        vendor: "anthropic",
      },
      {
        name: "OpenAI Provider",
        provider: "openai",
        providerId: "openai-1",
        providerDisplayName: "ChatGPT (OpenAI)",
        modelName: "gpt-4o-mini",
        displayName: "GPT-4o Mini",
        vendor: null,
      },
    ];

    const grouped = groupLlmOptions(options);

    expect(grouped.map((group) => group.key)).toEqual([
      "bedrock/anthropic",
      "openai/openai-1",
    ]);
    expect(grouped[0]?.displayName).toBe("Amazon Bedrock/Anthropic");
    expect(grouped[1]?.displayName).toBe("OpenAI Provider");
    expect(grouped[0]?.options).toHaveLength(1);
    expect(grouped[1]?.options).toHaveLength(1);
  });
});
