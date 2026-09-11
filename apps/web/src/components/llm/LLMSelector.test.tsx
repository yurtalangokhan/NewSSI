import React from "react";
import { render, screen } from "@tests/setup/test-utils";
import LLMSelector from "./LLMSelector";
import { LLMProviderDescriptor } from "@/interfaces/llm";

describe("LLMSelector", () => {
  it("excludes models with supports_embedding flag", () => {
    const providers: LLMProviderDescriptor[] = [
      {
        id: 1,
        name: "Ollama",
        provider: "ollama",
        provider_display_name: "Ollama",
        model_configurations: [
          {
            name: "llama3.2:latest",
            display_name: "Llama 3.2",
            is_visible: true,
            max_input_tokens: 8192,
            supports_image_input: false,
            supports_reasoning: false,
            supports_embedding: false,
          },
          {
            name: "nomic-embed-text:latest",
            display_name: "Nomic Embed",
            is_visible: true,
            max_input_tokens: 2048,
            supports_image_input: false,
            supports_reasoning: false,
            supports_embedding: true,
          },
        ],
      },
    ];

    render(
      <LLMSelector
        llmProviders={providers}
        currentLlm="Ollama__ollama__llama3.2:latest"
        onSelect={jest.fn()}
      />
    );

    expect(screen.getAllByText("Llama 3.2")[0]).toBeInTheDocument();
    expect(screen.queryByText("Nomic Embed")).not.toBeInTheDocument();
  });
});
