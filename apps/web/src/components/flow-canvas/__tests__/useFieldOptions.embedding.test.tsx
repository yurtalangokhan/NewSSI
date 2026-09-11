import { renderHook } from "@testing-library/react";
import { useFieldOptions } from "../fields/useFieldOptions";
import { InputField } from "../types/componentTemplate";
import * as useResolvedOptionsModule from "../hooks/useResolvedOptions";

jest.mock("../hooks/useResolvedOptions");

describe("useFieldOptions - embedding model filtering", () => {
  it("filters out embedding models for llm.models source", () => {
    jest.spyOn(useResolvedOptionsModule, "useResolvedOptions").mockReturnValue({
      data: {
        source: "llm.models",
        available: true,
        items: [
          { value: "gpt-4o", label: "GPT-4o" },
          {
            value: "text-embedding-3-small",
            label: "Text Embedding 3 Small",
            supports_embedding: true,
          } as any,
        ],
      },
      isLoading: false,
      error: undefined,
      isValidating: false,
      mutate: jest.fn(),
    });

    const field: InputField = {
      type: "options",
      display_name: "Model",
      required: true,
      options_source: "llm.models",
      value: null,
      options: null,
      info: null,
      advanced: false,
      min: null,
      max: null,
    };

    const { result } = renderHook(() => useFieldOptions(field));

    expect(result.current.options).toHaveLength(1);
    expect(result.current.options[0]?.value).toBe("gpt-4o");
  });
});
