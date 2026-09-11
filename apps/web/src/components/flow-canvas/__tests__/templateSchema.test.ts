/**
 * Tests for templateSchema.ts — mirrors the backend's
 * domain/flows/handles.py: which output handles a node really has (dynamic
 * ports expand one-per-row), and whether a field is visible (show_when).
 *
 * The first four `getEffectiveOutputHandles` expectations are the regression
 * gate: the Router special case became a declaration, behaviour must not.
 */

import type { ComponentTemplate } from "../types/componentTemplate";
import {
  fieldVisible,
  getEffectiveInputHandles,
  getEffectiveOutputHandles,
  resolvedValues,
  visibleInputs,
} from "../utils/templateSchema";

function routerTemplate(): ComponentTemplate {
  return {
    type: "Router",
    category: "logic",
    display_name: "Router",
    description: "",
    icon: null,
    template_version: 1,
    lifecycle: "stable",
    kind: "execution",
    inputs: {},
    handles: {
      inputs: [{ name: "message", types: ["Message"] }],
      outputs: [
        {
          name: "routes",
          types: ["Trigger"],
          expands_from: "routes",
          expands_label_key: "route",
        },
      ],
    },
  };
}

describe("getEffectiveOutputHandles — non-expanding", () => {
  it("returns the template's declared outputs unchanged", () => {
    const template: ComponentTemplate = {
      ...routerTemplate(),
      type: "ZeroShotAgent",
      handles: {
        inputs: [],
        outputs: [{ name: "message", types: ["Message"] }],
      },
    };
    expect(getEffectiveOutputHandles(template, {})).toEqual(
      template.handles.outputs
    );
  });
});

describe("getEffectiveOutputHandles — dynamic expansion", () => {
  it("expands the single declared handle into one per configured route", () => {
    const template = routerTemplate();
    const values = {
      routes: [
        { condition: "x > 1", route: "high" },
        { condition: "x <= 1", route: "low" },
      ],
    };
    expect(getEffectiveOutputHandles(template, values)).toEqual([
      { name: "high", types: ["Trigger"] },
      { name: "low", types: ["Trigger"] },
    ]);
  });

  it("falls back to the declared handle when no routes are configured yet", () => {
    const template = routerTemplate();
    expect(getEffectiveOutputHandles(template, { routes: [] })).toEqual([
      { name: "routes", types: ["Trigger"] },
    ]);
  });

  it("ignores rows with a blank or missing route label", () => {
    const template = routerTemplate();
    const values = {
      routes: [
        { condition: "a", route: "" },
        { condition: "b", route: "ok" },
      ],
    };
    expect(getEffectiveOutputHandles(template, values)).toEqual([
      { name: "ok", types: ["Trigger"] },
    ]);
  });

  it("handles a template with no declared output at all", () => {
    const template: ComponentTemplate = {
      ...routerTemplate(),
      handles: { inputs: [], outputs: [] },
    };
    expect(
      getEffectiveOutputHandles(template, { routes: [{ route: "x" }] })
    ).toEqual([]);
  });
});

describe("conditional output handles (Handle.show_when)", () => {
  const smartRouterish = (): ComponentTemplate => ({
    ...routerTemplate(),
    type: "SmartRouter",
    inputs: {
      enable_else_output: {
        type: "bool",
        display_name: "Else",
        required: false,
        value: false,
        options: null,
        options_source: null,
        info: null,
        advanced: false,
        min: null,
        max: null,
      } as any,
    },
    handles: {
      inputs: [{ name: "message", types: ["Message"] }],
      outputs: [
        {
          name: "routes",
          types: ["Message"],
          expands_from: "routes",
          expands_label_key: "route_category",
        },
        {
          name: "else",
          types: ["Message"],
          show_when: { field: "enable_else_output", equals: true },
        },
      ],
    },
  });

  it("drops the else port when the toggle is off", () => {
    const names = getEffectiveOutputHandles(smartRouterish(), {
      routes: [{ route_category: "billing" }],
    }).map((h) => h.name);
    expect(names).toEqual(["billing"]);
  });

  it("keeps the else port when the toggle is on", () => {
    const names = getEffectiveOutputHandles(smartRouterish(), {
      enable_else_output: true,
      routes: [{ route_category: "billing" }],
    }).map((h) => h.name);
    expect(names).toEqual(["billing", "else"]);
  });
});

describe("field visibility", () => {
  const field = (show_when?: any) =>
    ({
      type: "bool",
      display_name: "Case sensitive",
      required: false,
      value: true,
      options: null,
      options_source: null,
      info: null,
      advanced: false,
      min: null,
      max: null,
      show_when: show_when ?? null,
    }) as any;

  it("is visible when no rule is declared", () => {
    expect(fieldVisible(field(), {})).toBe(true);
  });

  it("hides on not_equals match", () => {
    const f = field({ field: "operator", not_equals: "regex" });
    expect(fieldVisible(f, { operator: "regex" })).toBe(false);
    expect(fieldVisible(f, { operator: "contains" })).toBe(true);
  });

  it("resolves template defaults before judging visibility", () => {
    const template = {
      ...routerTemplate(),
      inputs: {
        operator: {
          type: "str",
          display_name: "Op",
          required: false,
          value: "regex",
          options: null,
          options_source: null,
          info: null,
          advanced: false,
          min: null,
          max: null,
        },
        case_sensitive: field({ field: "operator", not_equals: "regex" }),
      },
    } as any;
    expect(Object.keys(visibleInputs(template, {}))).toEqual(["operator"]);
    expect(
      Object.keys(visibleInputs(template, { operator: "contains" })).sort()
    ).toEqual(["case_sensitive", "operator"]);
    expect(resolvedValues(template, {})).toEqual({
      operator: "regex",
      case_sensitive: true,
    });
  });
});

/**
 * Input handles — the mirror of the output resolver (Phase 4.5).
 *
 * These cases are deliberately identical to the backend's
 * tests/domain/flows/test_handles.py. Phase 0's route/label bug was two sides
 * that were each internally consistent and separately tested; parallel case
 * lists are the guard against repeating it.
 */
function conditionalInputTemplate(): ComponentTemplate {
  return {
    type: "X",
    category: "logic",
    display_name: "X",
    description: "",
    icon: null,
    template_version: 1,
    lifecycle: "stable",
    kind: "execution",
    inputs: { on: { type: "bool", display_name: "On", value: false } },
    handles: {
      inputs: [
        { name: "always", types: ["Message"] },
        {
          name: "maybe",
          types: ["Message"],
          show_when: { field: "on", equals: true },
        },
      ],
      outputs: [],
    },
  } as unknown as ComponentTemplate;
}

describe("getEffectiveInputHandles", () => {
  it("respects show_when on input handles", () => {
    const template = conditionalInputTemplate();
    expect(getEffectiveInputHandles(template, {}).map((h) => h.name)).toEqual([
      "always",
    ]);
    expect(
      getEffectiveInputHandles(template, { on: true }).map((h) => h.name)
    ).toEqual(["always", "maybe"]);
  });

  it("is total for a hand-edited spec", () => {
    const template = conditionalInputTemplate();
    expect(
      getEffectiveInputHandles(template, { on: "evet" }).map((h) => h.name)
    ).toEqual(["always"]);
  });
});
