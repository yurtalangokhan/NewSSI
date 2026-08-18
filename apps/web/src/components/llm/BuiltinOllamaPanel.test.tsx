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
          {
            name: "qwen2.5vl:3b",
            display_name: "qwen2.5vl:3b",
            size: 3_200_000_000,
            max_input_tokens: 128000,
            supports_image_input: true,
            supports_reasoning: false,
            supports_tools: true,
            is_remote: false,
          },
          {
            name: "nomic-embed-text:latest",
            display_name: "nomic-embed-text:latest",
            size: 274_000_000,
            max_input_tokens: 8192,
            supports_image_input: false,
            supports_reasoning: false,
            supports_embedding: true,
            is_remote: false,
          },
          {
            name: "qwen2.5-coder:7b",
            display_name: "qwen2.5-coder:7b",
            size: 4_700_000_000,
            max_input_tokens: 32768,
            supports_image_input: false,
            supports_reasoning: false,
            supports_code: true,
            is_remote: true,
          },
          {
            name: "whisper:latest",
            display_name: "whisper:latest",
            size: 1_500_000_000,
            max_input_tokens: 448,
            supports_image_input: false,
            supports_reasoning: false,
            supports_audio: true,
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
    expect(screen.getByText("reasoning")).toBeInTheDocument();
    expect(screen.getByText("qwen2.5vl:3b")).toBeInTheDocument();
    expect(screen.getByText("vision")).toBeInTheDocument();
    expect(screen.getByText("tools")).toBeInTheDocument();
    expect(screen.getByText("128,000 ctx")).toBeInTheDocument();
    expect(screen.getByText("nomic-embed-text:latest")).toBeInTheDocument();
    expect(screen.getByText("embedding")).toBeInTheDocument();
    expect(screen.getByText("qwen2.5-coder:7b")).toBeInTheDocument();
    expect(screen.getByText("code")).toBeInTheDocument();
    expect(screen.getByText("cloud")).toBeInTheDocument();
    expect(screen.getByText("whisper:latest")).toBeInTheDocument();
    expect(screen.getByText("audio")).toBeInTheDocument();
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
