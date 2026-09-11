/**
 * Tests for componentSearch.ts.
 *
 * Brief: .tmp/flow-canvas-task-25-brief.md
 */

import {
  filterGroupedTemplates,
  matchesSearch,
} from "../utils/componentSearch";
import type { ComponentTemplate } from "../types/componentTemplate";

function template(
  type: string,
  display_name: string,
  description = ""
): ComponentTemplate {
  return {
    type,
    category: "core",
    display_name,
    description,
    icon: null,
    template_version: 1,
    lifecycle: "stable",
    kind: "execution",
    inputs: {},
    handles: { inputs: [], outputs: [] },
  };
}

describe("matchesSearch (25.2)", () => {
  it("matches on display name", () => {
    const t = template("ChatInput", "Chat Input");
    expect(matchesSearch("chat", t)).toBe(true);
  });

  it("matches on description", () => {
    const t = template("ChatInput", "Chat Input", "Accepts a user message");
    expect(matchesSearch("message", t)).toBe(true);
  });

  it("an empty query matches everything", () => {
    const t = template("ChatInput", "Chat Input");
    expect(matchesSearch("", t)).toBe(true);
    expect(matchesSearch("   ", t)).toBe(true);
  });

  it("does not match unrelated text", () => {
    const t = template("ChatInput", "Chat Input");
    expect(matchesSearch("database", t)).toBe(false);
  });
});

describe("matchesSearch (25.3) — tolerates partial and misordered terms", () => {
  it("matches regardless of term order", () => {
    const t = template("ChatInput", "Chat Input");
    expect(matchesSearch("input chat", t)).toBe(true);
  });

  it("matches on a partial word", () => {
    const t = template("ZeroShotAgent", "Zero-Shot Agent");
    expect(matchesSearch("zero", t)).toBe(true);
    expect(matchesSearch("shot agent", t)).toBe(true);
  });

  it("is case-insensitive and ignores underscores/hyphens", () => {
    const t = template("SelfReflectAgent", "Self-Reflect Agent");
    expect(matchesSearch("SELF REFLECT", t)).toBe(true);
  });
});

describe("filterGroupedTemplates", () => {
  it("drops categories with no matches and keeps only matching items", () => {
    const grouped = {
      core: [
        template("ChatInput", "Chat Input"),
        template("ChatOutput", "Chat Output"),
      ],
      agents: [template("ZeroShotAgent", "Zero-Shot Agent")],
    };

    const filtered = filterGroupedTemplates(grouped, "chat");

    expect(Object.keys(filtered)).toEqual(["core"]);
    expect(filtered.core).toHaveLength(2);
  });

  it("returns everything unfiltered for an empty query", () => {
    const grouped = { core: [template("ChatInput", "Chat Input")] };

    expect(filterGroupedTemplates(grouped, "")).toEqual(grouped);
  });

  it("returns an empty object when nothing matches anywhere", () => {
    const grouped = { core: [template("ChatInput", "Chat Input")] };

    expect(filterGroupedTemplates(grouped, "nonexistent")).toEqual({});
  });
});
