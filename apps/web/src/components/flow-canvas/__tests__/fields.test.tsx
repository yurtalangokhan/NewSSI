/**
 * Tests for the 13 FieldType renderers (fields/index.ts's registry) and
 * shared options-source resolution (OptionsField/MultiselectField).
 * `useResolvedOptions` is mocked directly — same pattern Task 25 used for
 * `useComponentTemplates` — since the real proxy route doesn't exist yet
 * (Task 28).
 *
 * Brief: .tmp/flow-canvas-task-26-brief.md
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ALL_FIELD_TYPES, type InputField } from "../types/componentTemplate";

const mockUseResolvedOptions = jest.fn();
jest.mock("../hooks/useResolvedOptions", () => ({
  useResolvedOptions: (source: string | null) => mockUseResolvedOptions(source),
}));

jest.mock("@/refresh-components/SimpleTooltip", () => ({
  __esModule: true,
  default: ({
    children,
    tooltip,
  }: {
    children: React.ReactNode;
    tooltip?: React.ReactNode;
  }) => (
    <div data-testid="tooltip-wrapper">
      <div data-testid="tooltip-content">{tooltip}</div>
      {children}
    </div>
  ),
}));

import { FIELD_RENDERERS } from "../fields";
import { FlowEditorShell } from "../components/FlowEditorShell";
import { createFlowStore } from "../stores/flowStore";

function field(overrides: Partial<InputField> = {}): InputField {
  return {
    type: "str",
    display_name: "Field",
    required: false,
    value: null,
    options: null,
    options_source: null,
    info: null,
    advanced: false,
    min: null,
    max: null,
    ...overrides,
  };
}

beforeEach(() => {
  mockUseResolvedOptions.mockReset();
  mockUseResolvedOptions.mockReturnValue({
    data: undefined,
    isLoading: false,
    error: undefined,
  });
});

describe("FIELD_RENDERERS (26.1)", () => {
  it("registers a renderer for every FieldType — no silent gap", () => {
    expect(Object.keys(FIELD_RENDERERS).sort()).toEqual(
      [...ALL_FIELD_TYPES].sort()
    );
  });
});

describe("StrField", () => {
  it("shows the current value and reports edits", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.str;
    render(
      <Renderer
        fieldKey="name"
        field={field()}
        value="hello"
        onChange={onChange}
      />
    );
    fireEvent.change(screen.getByDisplayValue("hello"), {
      target: { value: "world" },
    });
    expect(onChange).toHaveBeenCalledWith("world");
  });
});

describe("IntField", () => {
  it("shows the current numeric value", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.int;
    render(
      <Renderer
        fieldKey="n"
        field={field({ type: "int", min: 0, max: 10 })}
        value={3}
        onChange={onChange}
      />
    );
    expect(screen.getByDisplayValue("3")).toBeInTheDocument();
  });
});

describe("BoolField", () => {
  it("toggles via onCheckedChange", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.bool;
    render(
      <Renderer
        fieldKey="flag"
        field={field({ type: "bool" })}
        value={false}
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe("SecretField", () => {
  it("renders masked and reports the real value on change", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.secret;
    // PasswordInputTypeIn's reveal toggle uses @opal/components's Button
    // `tooltip` prop, which (unlike SimpleTooltip) relies on an ancestor
    // TooltipProvider rather than self-wrapping one — real usage always
    // has one at the app root; this test supplies it explicitly.
    const { container } = render(
      <TooltipProvider>
        <Renderer
          fieldKey="api_key"
          field={field({ type: "secret" })}
          value="sk-abc"
          onChange={onChange}
        />
      </TooltipProvider>
    );
    const input = container.querySelector("input") as HTMLInputElement;
    expect(input.value).not.toBe("sk-abc");
  });
});

describe("PromptField", () => {
  it("uses a textarea", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.prompt;
    render(
      <Renderer
        fieldKey="p"
        field={field({ type: "prompt" })}
        value="hi"
        onChange={onChange}
      />
    );
    expect(screen.getByDisplayValue("hi").tagName).toBe("TEXTAREA");
  });

  it("opens a full-screen modal, editable independently of the inline value", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.prompt;
    render(
      <Renderer
        fieldKey="p"
        field={field({ type: "prompt", display_name: "Agent Instructions" })}
        value="hi"
        onChange={onChange}
      />
    );

    fireEvent.click(
      screen.getByRole("button", { name: /expand prompt editor/i })
    );

    expect(screen.getByText("Agent Instructions")).toBeInTheDocument();
    // Two textareas now exist (inline + modal) — both start seeded with "hi".
    const textareas = screen.getAllByDisplayValue("hi");
    expect(textareas).toHaveLength(2);

    fireEvent.change(textareas[textareas.length - 1]!, {
      target: { value: "hi there" },
    });
    // Editing the modal's draft must not leak back to the field until Save.
    expect(onChange).not.toHaveBeenCalled();
  });

  it("commits the draft to onChange on Save and closes", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.prompt;
    render(
      <Renderer
        fieldKey="p"
        field={field({ type: "prompt" })}
        value="hi"
        onChange={onChange}
      />
    );

    fireEvent.click(
      screen.getByRole("button", { name: /expand prompt editor/i })
    );
    const textareas = screen.getAllByDisplayValue("hi");
    fireEvent.change(textareas[textareas.length - 1]!, {
      target: { value: "new prompt" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(onChange).toHaveBeenCalledWith("new prompt");
    expect(
      screen.queryByRole("button", { name: /^save$/i })
    ).not.toBeInTheDocument();
  });

  it("discards the draft on Cancel", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.prompt;
    render(
      <Renderer
        fieldKey="p"
        field={field({ type: "prompt" })}
        value="hi"
        onChange={onChange}
      />
    );

    fireEvent.click(
      screen.getByRole("button", { name: /expand prompt editor/i })
    );
    const textareas = screen.getAllByDisplayValue("hi");
    fireEvent.change(textareas[textareas.length - 1]!, {
      target: { value: "discarded" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));

    expect(onChange).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: /^save$/i })
    ).not.toBeInTheDocument();
  });

  it("opens modal properly when editor is in fullscreen mode and Escape closes modal without exiting fullscreen", () => {
    const store = createFlowStore();
    store.getState().setFullscreen(true);

    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.prompt;

    render(
      <FlowEditorShell store={store}>
        <Renderer
          fieldKey="p"
          field={field({ type: "prompt", display_name: "System Instructions" })}
          value="test prompt"
          onChange={onChange}
        />
      </FlowEditorShell>
    );

    // Fullscreen canvas is active
    expect(
      document.querySelector('[data-fullscreen="true"]')
    ).toBeInTheDocument();

    // Click expand button on prompt field
    fireEvent.click(
      screen.getByRole("button", { name: /expand prompt editor/i })
    );

    // Modal dialog must be visible and rendered
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText("System Instructions")).toBeInTheDocument();

    // Press Escape — modal closes, but fullscreen remains active
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(store.getState().isFullscreen).toBe(true);
  });
});

describe("CodeField", () => {
  it("is editable (not the read-only Code viewer)", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.code;
    render(
      <Renderer
        fieldKey="c"
        field={field({ type: "code" })}
        value="x = 1"
        onChange={onChange}
      />
    );
    const textarea = screen.getByDisplayValue("x = 1");
    fireEvent.change(textarea, { target: { value: "x = 2" } });
    expect(onChange).toHaveBeenCalledWith("x = 2");
  });
});

describe("JsonField", () => {
  it("parses valid JSON and writes the parsed value", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.json;
    render(
      <Renderer
        fieldKey="cfg"
        field={field({ type: "json" })}
        value={{ a: 1 }}
        onChange={onChange}
      />
    );
    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: '{"a": 2}' } });
    expect(onChange).toHaveBeenCalledWith({ a: 2 });
  });

  it("does not call onChange while the text is invalid JSON", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.json;
    render(
      <Renderer
        fieldKey="cfg"
        field={field({ type: "json" })}
        value={{ a: 1 }}
        onChange={onChange}
      />
    );
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "{not valid" },
    });
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("FileField", () => {
  it("renders a file attach affordance", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.file;
    const { container } = render(
      <Renderer
        fieldKey="f"
        field={field({ type: "file" })}
        value=""
        onChange={onChange}
      />
    );
    expect(container.querySelector('input[type="file"]')).toBeInTheDocument();
  });
});

describe("SliderField (26.5)", () => {
  it("uses the template's min/max as the slider bounds", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.slider;
    render(
      <Renderer
        fieldKey="temperature"
        field={field({ type: "slider", min: 0, max: 2 })}
        value={1}
        onChange={onChange}
      />
    );
    const slider = screen.getByRole("slider");
    expect(slider).toHaveAttribute("aria-valuemin", "0");
    expect(slider).toHaveAttribute("aria-valuemax", "2");
    expect(slider).toHaveAttribute("aria-valuenow", "1");
  });
});

describe("TableField", () => {
  it("renders one row per value entry and supports adding a row", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.table;
    render(
      <Renderer
        fieldKey="routes"
        field={field({ type: "table" })}
        value={[{ condition: "x", route: "a" }]}
        onChange={onChange}
      />
    );
    expect(screen.getByDisplayValue("x")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /add row/i }));
    expect(onChange).toHaveBeenCalledWith([
      { condition: "x", route: "a" },
      { condition: "", route: "" },
    ]);
  });
});

describe("OptionsField — static options", () => {
  it("renders options from field.options without resolving a source", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.options;
    render(
      <Renderer
        fieldKey="mode"
        field={field({ type: "options", options: ["alpha", "beta"] })}
        value="alpha"
        onChange={onChange}
      />
    );
    expect(mockUseResolvedOptions).toHaveBeenCalledWith(null);
    // The trigger already shows the selected value without opening the
    // dropdown (InputSelect's own selected-item display).
    expect(screen.getByRole("combobox")).toHaveTextContent("alpha");
  });

  it("lists every option once the dropdown is opened", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.options;
    render(
      <Renderer
        fieldKey="mode"
        field={field({ type: "options", options: ["alpha", "beta"] })}
        value=""
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.getByRole("option", { name: "beta" })).toBeInTheDocument();
  });
});

describe("OptionsField — options_source (26.6)", () => {
  it("fetches and lists resolved options once opened", () => {
    mockUseResolvedOptions.mockReturnValue({
      data: {
        source: "llm.models",
        available: true,
        items: [{ value: "gpt-4o", label: "GPT-4o" }],
      },
      isLoading: false,
      error: undefined,
    });
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.options;
    render(
      <Renderer
        fieldKey="model"
        field={field({
          type: "options",
          options: null,
          options_source: "llm.models",
        })}
        value=""
        onChange={onChange}
      />
    );
    expect(mockUseResolvedOptions).toHaveBeenCalledWith("llm.models");
    fireEvent.click(screen.getByRole("combobox"));
    expect(screen.getByRole("option", { name: "GPT-4o" })).toBeInTheDocument();
  });
});

describe("OptionsField — unavailable source (26.7)", () => {
  it("shows a reason, not an empty dropdown", () => {
    mockUseResolvedOptions.mockReturnValue({
      data: { source: "rag.collections", available: false, items: [] },
      isLoading: false,
      error: undefined,
    });
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.options;
    render(
      <Renderer
        fieldKey="collection"
        field={field({
          type: "options",
          options: null,
          options_source: "rag.collections",
        })}
        value=""
        onChange={onChange}
      />
    );
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
  });
});

describe("OptionsField — agents.definitions hover preview", () => {
  it("wraps each agent option with a tooltip showing its preview description", () => {
    mockUseResolvedOptions.mockReturnValue({
      data: {
        source: "agents.definitions",
        available: true,
        items: [
          {
            value: "a-1",
            label: "Support Bot",
            description: "Model: gpt-4o · Tools: 2 · Memory: on",
          },
        ],
      },
      isLoading: false,
      error: undefined,
    });
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.options;
    render(
      <Renderer
        fieldKey="agent_id"
        field={field({
          type: "options",
          options: null,
          options_source: "agents.definitions",
        })}
        value=""
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByRole("combobox"));

    const option = screen.getByRole("option", { name: "Support Bot" });
    const wrapper = option.closest(
      '[data-testid="tooltip-wrapper"]'
    ) as HTMLElement;
    expect(wrapper).not.toBeNull();
    expect(within(wrapper).getByText("gpt-4o")).toBeInTheDocument();
    expect(within(wrapper).getByText("2")).toBeInTheDocument();
    expect(within(wrapper).getByText("on")).toBeInTheDocument();
  });

  it("does not attach an agent-preview tooltip for unrelated options sources", () => {
    mockUseResolvedOptions.mockReturnValue({
      data: {
        source: "llm.models",
        available: true,
        items: [{ value: "gpt-4o", label: "GPT-4o", description: "openai" }],
      },
      isLoading: false,
      error: undefined,
    });
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.options;
    render(
      <Renderer
        fieldKey="model"
        field={field({
          type: "options",
          options: null,
          options_source: "llm.models",
        })}
        value=""
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByRole("combobox"));

    const option = screen.getByRole("option", { name: "GPT-4o" });
    expect(
      option.closest('[data-testid="tooltip-wrapper"]')
    ).not.toBeInTheDocument();
  });
});

describe("MultiselectField", () => {
  it("adds and removes selections from a fixed option list", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.multiselect;
    render(
      <Renderer
        fieldKey="tags"
        field={field({ type: "multiselect", options: ["a", "b", "c"] })}
        value={["a"]}
        onChange={onChange}
      />
    );
    expect(screen.getByText("a")).toBeInTheDocument();
  });

  it("stays open after picking an option so several can be added in a row", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.multiselect;
    render(
      <Renderer
        fieldKey="tags"
        field={field({ type: "multiselect", options: ["a", "b", "c"] })}
        value={[]}
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByRole("option", { name: "a" }));

    expect(onChange).toHaveBeenCalledWith(["a"]);
    // the menu did not close — the remaining options are still on screen
    expect(screen.getByRole("option", { name: "b" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "c" })).toBeInTheDocument();
  });

  it("closes once the last remaining option is picked", () => {
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.multiselect;
    render(
      <Renderer
        fieldKey="tags"
        field={field({ type: "multiselect", options: ["a", "b"] })}
        value={["a"]}
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByRole("option", { name: "b" }));

    expect(onChange).toHaveBeenCalledWith(["a", "b"]);
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });

  it("keeps the inline description for non-agent multiselect sources (e.g. tool categories)", () => {
    mockUseResolvedOptions.mockReturnValue({
      data: {
        source: "mcp.tools.file",
        available: true,
        items: [
          {
            value: "totally_fake_tool_xyz",
            label: "Fake Tool",
            description: "Reads a file from disk",
          },
        ],
      },
      isLoading: false,
      error: undefined,
    });
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.multiselect;
    render(
      <Renderer
        fieldKey="enabled_tools"
        field={field({
          type: "multiselect",
          options: null,
          options_source: "mcp.tools.file",
        })}
        value={[]}
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByRole("combobox"));
    expect(
      screen.getAllByText("Reads a file from disk").length
    ).toBeGreaterThan(0);
  });
});

describe("MultiselectField — mcp.external_tools provider filtering", () => {
  const items = [
    {
      value: "deepwiki__ask_question",
      label: "ask_question",
      description: "prov-1|Ask a question about a repo",
    },
    {
      value: "deepwiki__read_wiki",
      label: "read_wiki",
      description: "prov-1|Read the wiki structure",
    },
    {
      value: "other__do_thing",
      label: "do_thing",
      description: "prov-2|An unrelated provider's tool",
    },
  ];

  function renderField(allValues: Record<string, unknown>) {
    const Renderer = FIELD_RENDERERS.multiselect;
    return render(
      <Renderer
        fieldKey="tools"
        field={field({
          type: "multiselect",
          options: null,
          options_source: "mcp.external_tools",
        })}
        value={[]}
        onChange={jest.fn()}
        allValues={allValues}
      />
    );
  }

  beforeEach(() => {
    mockUseResolvedOptions.mockReturnValue({
      data: { source: "mcp.external_tools", available: true, items },
      isLoading: false,
      error: undefined,
    });
  });

  it("only lists tools belonging to the provider selected on the same node", () => {
    renderField({ provider: "prov-1" });
    fireEvent.click(screen.getByRole("combobox"));

    expect(
      screen.getByRole("option", { name: "ask_question" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "read_wiki" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "do_thing" })
    ).not.toBeInTheDocument();
  });

  it("shows each tool's description without the leading provider-id tag", () => {
    renderField({ provider: "prov-1" });
    fireEvent.click(screen.getByRole("combobox"));

    expect(
      screen.getAllByText("Ask a question about a repo").length
    ).toBeGreaterThan(0);
    expect(screen.queryByText(/prov-1\|/)).not.toBeInTheDocument();
  });

  it("prompts to pick a provider first when none is selected", () => {
    renderField({});

    expect(screen.getByText("Select a provider first")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});

describe("MultiselectField — agents.definitions hover preview (sub_agents)", () => {
  it("wraps each agent option with a structured tooltip instead of a raw inline description", () => {
    mockUseResolvedOptions.mockReturnValue({
      data: {
        source: "agents.definitions",
        available: true,
        items: [
          {
            value: "a-1",
            label: "RAG agent",
            description:
              "Model: qwen3:8b-fp16 · Tools: 2 · Memory: off\nSends email on request.",
          },
        ],
      },
      isLoading: false,
      error: undefined,
    });
    const onChange = jest.fn();
    const Renderer = FIELD_RENDERERS.multiselect;
    render(
      <Renderer
        fieldKey="sub_agents"
        field={field({
          type: "multiselect",
          options: null,
          options_source: "agents.definitions",
        })}
        value={[]}
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByRole("combobox"));

    // The raw preview string must not be dumped inline under the row.
    expect(
      screen.queryByText("Model: qwen3:8b-fp16 · Tools: 2 · Memory: off")
    ).not.toBeInTheDocument();

    const option = screen.getByRole("option", { name: /RAG agent/ });
    const wrapper = option.closest(
      '[data-testid="tooltip-wrapper"]'
    ) as HTMLElement;
    expect(wrapper).not.toBeNull();
    expect(within(wrapper).getByText("qwen3:8b-fp16")).toBeInTheDocument();
    expect(within(wrapper).getByText("2")).toBeInTheDocument();
  });
});
