import React from "react";
import { render, screen, setupUser, waitFor } from "@tests/setup/test-utils";
import {
  BuiltinOllamaPanel,
  BuiltinOllamaPanelView,
} from "@/sections/llmConfig/BuiltinOllamaPanel";
import * as providerHooks from "@/hooks/useProviders";

jest.mock("@/hooks/useProviders", () => ({
  ...jest.requireActual("@/hooks/useProviders"),
  useBuiltinOllamaStatus: jest.fn(),
  useBuiltinOllamaModels: jest.fn(),
  useDeleteBuiltinOllamaModel: jest.fn(),
}));

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

  test("triggers onDeleteModel callback when trash icon is clicked", async () => {
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

    await user.click(
      screen.getByRole("button", { name: "Delete llama3.1:8b" })
    );

    expect(onDeleteModel).toHaveBeenCalledWith("llama3.1:8b");
  });
});

describe("BuiltinOllamaPanel (Integration with Confirmation Modal)", () => {
  const mockDeleteModel = jest.fn();
  const mockStatusMutate = jest.fn();
  const mockModelsMutate = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    (providerHooks.useBuiltinOllamaStatus as jest.Mock).mockReturnValue({
      data: {
        base_url: "http://ollama:11434",
        online: true,
        version: "0.6.8",
        model_count: 1,
        error: null,
      },
      isLoading: false,
      mutate: mockStatusMutate,
    });
    (providerHooks.useBuiltinOllamaModels as jest.Mock).mockReturnValue({
      data: [
        {
          name: "llama3.1:8b",
          display_name: "llama3.1:8b",
          size: 4_900_000_000,
          max_input_tokens: 131072,
        },
      ],
      isLoading: false,
      mutate: mockModelsMutate,
    });
    mockDeleteModel.mockResolvedValue({ success: true });
    (providerHooks.useDeleteBuiltinOllamaModel as jest.Mock).mockReturnValue(
      mockDeleteModel
    );
  });

  test("opens confirmation modal when delete icon is clicked and deletes on confirm", async () => {
    const user = setupUser();

    render(<BuiltinOllamaPanel onDownload={jest.fn()} />);

    // Click trash button on the model item
    await user.click(
      screen.getByRole("button", { name: "Delete llama3.1:8b" })
    );

    // Confirmation modal should be visible
    expect(screen.getByText("Delete Model")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Are you sure you want to delete the model "llama3.1:8b"/
      )
    ).toBeInTheDocument();

    // Confirm deletion
    const deleteSubmitButton = screen.getByRole("button", { name: "Delete" });
    await user.click(deleteSubmitButton);

    await waitFor(() => {
      expect(mockDeleteModel).toHaveBeenCalledWith("llama3.1:8b");
    });
  });

  test("can cancel deletion without invoking delete API", async () => {
    const user = setupUser();

    render(<BuiltinOllamaPanel onDownload={jest.fn()} />);

    await user.click(
      screen.getByRole("button", { name: "Delete llama3.1:8b" })
    );

    expect(screen.getByText("Delete Model")).toBeInTheDocument();

    // Click Cancel
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByText("Delete Model")).not.toBeInTheDocument();
    expect(mockDeleteModel).not.toHaveBeenCalled();
  });
});
