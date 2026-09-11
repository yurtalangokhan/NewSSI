/**
 * options_source dependencies.
 *
 * `llm.models` used to return every provider's models, and OptionsField
 * narrowed them client-side by splitting the `description` display string on
 * "|" and matching `a.includes(b) || b.includes(a)`. That made "openai" match
 * an "openai-compatible" provider, and when the filter matched nothing it
 * silently fell back to showing every model — so a wrong filter looked like a
 * working one.
 *
 * The narrowing now happens on the server, and these tests pin the wire
 * format that carries the dependency there.
 */

import { flowApi } from "../api/flowApi";
import {
  dependencyValues,
  optionsRequestKey,
} from "../fields/optionDependencies";
import type { InputField } from "../types/componentTemplate";

function field(overrides: Partial<InputField> = {}): InputField {
  return {
    type: "options",
    display_name: "Model",
    required: true,
    value: null,
    options: null,
    options_source: "llm.models",
    info: null,
    advanced: false,
    min: null,
    max: null,
    depends_on: ["provider"],
    ...overrides,
  } as unknown as InputField;
}

describe("dependencyValues", () => {
  it("picks only the sibling values the field declares", () => {
    expect(
      dependencyValues(field(), { provider: "openai", temperature: 0.7 })
    ).toEqual({ provider: "openai" });
  });

  it("is empty when the field declares no dependency", () => {
    expect(
      dependencyValues(field({ depends_on: null }), { provider: "openai" })
    ).toEqual({});
  });

  it("skips a dependency that has no value yet", () => {
    expect(dependencyValues(field(), {})).toEqual({});
    expect(dependencyValues(field(), { provider: "" })).toEqual({});
  });

  it("coerces a non-string value so the query string stays well formed", () => {
    expect(
      dependencyValues(field({ depends_on: ["top_k"] }), { top_k: 5 })
    ).toEqual({
      top_k: "5",
    });
  });

  it("tolerates missing values entirely", () => {
    expect(dependencyValues(field(), undefined)).toEqual({});
  });
});

describe("optionsRequestKey", () => {
  it("is the plain endpoint when there is no dependency", () => {
    expect(optionsRequestKey("llm.providers", {})).toBe(
      flowApi.componentOptions("llm.providers")
    );
  });

  it("appends one dep parameter per dependency", () => {
    expect(optionsRequestKey("llm.models", { provider: "openai" })).toBe(
      `${flowApi.componentOptions("llm.models")}?dep=provider%3Aopenai`
    );
  });

  it("orders dependencies so the same set always produces the same key", () => {
    const a = optionsRequestKey("llm.models", { b: "2", a: "1" });
    const b = optionsRequestKey("llm.models", { a: "1", b: "2" });
    expect(a).toBe(b);
  });

  it("changes when a dependency value changes, so the list refetches", () => {
    expect(optionsRequestKey("llm.models", { provider: "openai" })).not.toBe(
      optionsRequestKey("llm.models", { provider: "anthropic" })
    );
  });

  it("escapes a value that would otherwise break the query string", () => {
    expect(optionsRequestKey("llm.models", { provider: "a&b=c" })).toContain(
      encodeURIComponent("provider:a&b=c")
    );
  });
});
