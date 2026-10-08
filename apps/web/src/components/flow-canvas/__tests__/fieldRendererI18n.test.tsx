/**
 * The field renderers that show a field's *own* name — `StrField`'s
 * placeholder, `SliderField`'s aria-label, `PromptField`'s expanded-modal
 * title, `SecretField`'s reveal tooltips — must resolve it through the same
 * locale chain the visible label uses (`resolveFieldName`), not the server's
 * raw English `display_name`.
 *
 * `fields.test.tsx` renders without an `I18nextProvider`, so every
 * `t(key, default)` there returns the in-code default and a hardcoded
 * `display_name` is indistinguishable from a translated name. These tests
 * mount real locale instances to make the difference observable.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { I18nextProvider } from "react-i18next";
import { TooltipProvider } from "@/components/ui/tooltip";
import { createI18nInstance } from "@/i18n/config";
import { OptionsField } from "../fields/OptionsField";
import { PromptField } from "../fields/PromptField";
import { SecretField } from "../fields/SecretField";
import { SliderField } from "../fields/SliderField";
import { StrField } from "../fields/StrField";
import type { InputField } from "../types/componentTemplate";

/**
 * `OptionsField` resolves its list through this hook; these tests assert the
 * dropdown's placeholder copy, not the option data.
 */
jest.mock("../fields/useFieldOptions", () => ({
  useFieldOptions: () => ({
    options: [{ value: "gpt-4", label: "GPT-4" }],
    isLoading: false,
    unavailable: false,
  }),
}));

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

function renderIn(
  locale: "en" | "tr",
  node: ReactElement,
  extraResources?: Record<string, unknown>
) {
  const i18n = createI18nInstance(locale);
  if (extraResources) {
    i18n.addResourceBundle(locale, "common", extraResources, true, true);
  }
  return render(
    <I18nextProvider i18n={i18n}>
      <TooltipProvider>{node}</TooltipProvider>
    </I18nextProvider>
  );
}

describe("StrField placeholder i18n", () => {
  it("uses the locale copy of the field name in English", () => {
    renderIn(
      "en",
      <StrField
        fieldKey="system_prompt"
        field={field({ display_name: "System prompt" })}
        value=""
        onChange={jest.fn()}
      />
    );

    expect(screen.getByPlaceholderText("System Prompt")).toBeInTheDocument();
  });

  it("uses the Turkish copy instead of the server's English display_name", () => {
    renderIn(
      "tr",
      <StrField
        fieldKey="system_prompt"
        field={field({ display_name: "System prompt" })}
        value=""
        onChange={jest.fn()}
      />
    );

    expect(screen.getByPlaceholderText("Sistem İstemi")).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("System prompt")
    ).not.toBeInTheDocument();
  });

  it("prefers the component-scoped copy over the generic one", () => {
    renderIn(
      "tr",
      <StrField
        fieldKey="temperature"
        field={field({ display_name: "Temperature" })}
        componentType="LLMModel"
        value=""
        onChange={jest.fn()}
      />,
      {
        flowCanvas: {
          fields: { names: { LLMModel: { temperature: "Model Sıcaklığı" } } },
        },
      }
    );

    expect(screen.getByPlaceholderText("Model Sıcaklığı")).toBeInTheDocument();
  });

  it("falls back to the template display_name when no locale copy exists", () => {
    renderIn(
      "tr",
      <StrField
        fieldKey="not_a_translated_field"
        field={field({ display_name: "Widget Timeout" })}
        value=""
        onChange={jest.fn()}
      />
    );

    expect(screen.getByPlaceholderText("Widget Timeout")).toBeInTheDocument();
  });
});

describe("SliderField aria-label i18n", () => {
  it("labels the thumb with the Turkish field name", () => {
    renderIn(
      "tr",
      <SliderField
        fieldKey="temperature"
        field={field({
          type: "slider",
          display_name: "Temperature",
          min: 0,
          max: 2,
        })}
        value={1}
        onChange={jest.fn()}
      />
    );

    expect(screen.getByRole("slider")).toHaveAttribute(
      "aria-label",
      "Temperature (Yaratıcılık)"
    );
  });
});

describe("OptionsField dropdown placeholder i18n", () => {
  it("interpolates the Turkish field name, not the English display_name", () => {
    renderIn(
      "tr",
      <OptionsField
        fieldKey="model"
        field={field({
          type: "options",
          display_name: "Model Name",
          options: ["gpt-4"],
        })}
        value=""
        onChange={jest.fn()}
      />
    );

    expect(screen.getByText("Model seçin...")).toBeInTheDocument();
  });

  it("keeps the English sentence under the English locale", () => {
    renderIn(
      "en",
      <OptionsField
        fieldKey="model"
        field={field({
          type: "options",
          display_name: "Model Name",
          options: ["gpt-4"],
        })}
        value=""
        onChange={jest.fn()}
      />
    );

    expect(screen.getByText("Select Model...")).toBeInTheDocument();
  });
});

describe("PromptField expanded-modal title i18n", () => {
  it("titles the modal with the Turkish field name", () => {
    renderIn(
      "tr",
      <PromptField
        fieldKey="system_prompt"
        field={field({ type: "prompt", display_name: "System prompt" })}
        value="hi"
        onChange={jest.fn()}
      />
    );

    fireEvent.click(
      screen.getByRole("button", { name: "İstem Düzenleyiciyi Genişlet" })
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Sistem İstemi");
    expect(dialog).not.toHaveTextContent("System prompt");
  });
});

describe("SecretField reveal tooltips i18n", () => {
  it("uses the shared common copy for the reveal toggle in Turkish", () => {
    renderIn(
      "tr",
      <SecretField
        fieldKey="api_key"
        field={field({ type: "secret", display_name: "API key" })}
        value="sk-abc"
        onChange={jest.fn()}
      />
    );

    expect(
      screen.getByRole("button", { name: "Şifreyi göster" })
    ).toBeInTheDocument();
  });

  it("shows the hide label once the value is revealed", () => {
    renderIn(
      "tr",
      <SecretField
        fieldKey="api_key"
        field={field({ type: "secret", display_name: "API key" })}
        value="sk-abc"
        onChange={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Şifreyi göster" }));
    expect(
      screen.getByRole("button", { name: "Şifreyi gizle" })
    ).toBeInTheDocument();
  });
});
