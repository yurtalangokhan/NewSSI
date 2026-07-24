import React from "react";
import { render, screen, setupUser } from "@tests/setup/test-utils";
import { BuiltinOllamaPanelView } from "@/sections/llmConfig/BuiltinOllamaPanel";

describe("BuiltinOllamaPanelView", () => {
  test("renders built-in Ollama status and installed models", () => {
    render(
      <BuiltinOllamaPanelView
        status={{
          base_url: "http://ollama:11434",
          online: true,
          version: "0.6.8",
          model_count: 1,
          error: null,
        }}
        models={[
          {
            name: "llama3.1:8b",
            display_name: "llama3.1:8b",
            size: 4_900_000_000,
            max_input_tokens: 131072,
            supports_image_input: false,
            supports_reasoning: true,
            is_remote: false,
          },
        ]}
        isLoading={false}
        isDeleting={false}
        onRefresh={jest.fn()}
        onDownload={jest.fn()}
        onDeleteModel={jest.fn()}
      />
    );

    expect(screen.getByText("Ollama (Built-in)")).toBeInTheDocument();
    expect(screen.getAllByText("Online").length).toBeGreaterThan(0);
    expect(screen.getByText("http://ollama:11434")).toBeInTheDocument();
    expect(screen.getByText("llama3.1:8b")).toBeInTheDocument();
    expect(screen.getByText("131,072 ctx")).toBeInTheDocument();
  });

  test("deletes an installed model from the built-in service", async () => {
    const user = setupUser();
    const onDeleteModel = jest.fn();

    render(
      <BuiltinOllamaPanelView
        status={{
          base_url: "http://ollama:11434",
          online: true,
          version: "0.6.8",
          model_count: 1,
          error: null,
        }}
        models={[
          {
            name: "llama3.1:8b",
            display_name: "llama3.1:8b",
            size: 4_900_000_000,
            max_input_tokens: 131072,
            supports_image_input: false,
            supports_reasoning: false,
            is_remote: false,
          },
        ]}
        isLoading={false}
        isDeleting={false}
        onRefresh={jest.fn()}
        onDownload={jest.fn()}
        onDeleteModel={onDeleteModel}
      />
    );

    await user.click(screen.getByRole("button", { name: "Delete llama3.1:8b" }));

    expect(onDeleteModel).toHaveBeenCalledWith("llama3.1:8b");
  });
});
