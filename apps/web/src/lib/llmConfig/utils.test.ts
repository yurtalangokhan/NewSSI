import {
  resolveDefaultModelSelection,
  DefaultModelProviderGroup,
} from "./utils";

describe("resolveDefaultModelSelection", () => {
  const groups: DefaultModelProviderGroup[] = [
    {
      providerKey: "ollama",
      providerType: "ollama",
      models: ["qwen3:30b-a3b", "glm-4.7-flash:latest", "llama3.1:8b"],
    },
    {
      providerKey: "16289f82-5e0c-4d06-8549-bbecb50e00c1",
      providerType: "vllm",
      models: ["Qwen/Qwen3.5-27B"],
    },
  ];

  it("returns nothing when no default model is set", () => {
    expect(resolveDefaultModelSelection(null, null, groups)).toEqual({
      providerKey: undefined,
      modelName: undefined,
    });
  });

  it("uses the modern separate default_model + default_provider_id fields directly", () => {
    expect(
      resolveDefaultModelSelection("qwen3:30b-a3b", "ollama", groups)
    ).toEqual({ providerKey: "ollama", modelName: "qwen3:30b-a3b" });
  });

  it("parses the older 'providerId:modelName' composite format", () => {
    expect(
      resolveDefaultModelSelection(
        "16289f82-5e0c-4d06-8549-bbecb50e00c1:Qwen/Qwen3.5-27B",
        null,
        groups
      )
    ).toEqual({
      providerKey: "16289f82-5e0c-4d06-8549-bbecb50e00c1",
      modelName: "Qwen/Qwen3.5-27B",
    });
  });

  it("parses the Chat Preferences composite format written by structureValue, even when the model name itself contains a colon", () => {
    // Real data observed in production: saved via the Settings > Chat
    // Preferences model picker, which never sets default_provider_id.
    expect(
      resolveDefaultModelSelection(
        "Ollama__ollama__glm-4.7-flash:latest",
        null,
        groups
      )
    ).toEqual({ providerKey: "ollama", modelName: "glm-4.7-flash:latest" });
  });

  it("falls back to scanning all provider groups when only a bare model name is stored", () => {
    expect(
      resolveDefaultModelSelection("llama3.1:8b", null, groups)
    ).toEqual({ providerKey: "ollama", modelName: "llama3.1:8b" });
  });

  it("leaves providerKey unresolved when the saved model can't be found in any provider (e.g. provider deleted)", () => {
    const result = resolveDefaultModelSelection(
      "Deleted__deleted-provider__some-model",
      null,
      groups
    );
    expect(result.providerKey).toBeUndefined();
  });
});
