import {
  entityColor,
  entityColorVar,
} from "@/lib/knowledge-graph/entityPalette";

describe("entityColor", () => {
  it("gives common labels a fixed colour regardless of case", () => {
    expect(entityColor("Organization")).toBe("amber");
    expect(entityColor("policy")).toBe("blue");
    expect(entityColor("ROLE")).toBe("purple");
  });

  it("hashes unknown labels to a stable palette colour", () => {
    const first = entityColor("Regulation");

    expect(entityColor("Regulation")).toBe(first);
    expect([
      "cyan",
      "purple",
      "amber",
      "green",
      "blue",
      "orange",
      "red",
      "lime",
    ]).toContain(first);
  });
});

describe("entityColorVar", () => {
  it("builds the theme custom property for a shade", () => {
    expect(entityColorVar("green", "05")).toBe("var(--theme-green-05)");
    expect(entityColorVar("green", "01")).toBe("var(--theme-green-01)");
  });
});
