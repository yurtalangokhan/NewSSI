import {
  MERMAID_THEME_TOKENS,
  buildMermaidTheme,
  parseCssColor,
  toOpaqueHex,
} from "@/components/mermaid/mermaidTheme";

const WHITE = { r: 255, g: 255, b: 255, a: 1 };
const BLACK = { r: 0, g: 0, b: 0, a: 1 };

function reader(tokens: Record<string, string>) {
  return (token: string) => tokens[token] ?? "";
}

describe("parseCssColor", () => {
  it.each([
    ["#abc", { r: 170, g: 187, b: 204, a: 1 }],
    ["#286df8", { r: 40, g: 109, b: 248, a: 1 }],
    ["#000000e5", { r: 0, g: 0, b: 0, a: 229 / 255 }],
    ["rgb(163, 163, 163)", { r: 163, g: 163, b: 163, a: 1 }],
    ["rgba(0, 0, 0, 0.5)", { r: 0, g: 0, b: 0, a: 0.5 }],
    ["rgb(40 109 248 / 50%)", { r: 40, g: 109, b: 248, a: 0.5 }],
  ])("%s", (value, expected) => {
    expect(parseCssColor(value)).toEqual(expected);
  });

  it("rejects names and empty values (Mermaid only understands real colours)", () => {
    expect(parseCssColor("red")).toBeNull();
    expect(parseCssColor("")).toBeNull();
    expect(parseCssColor("var(--text-05)")).toBeNull();
  });
});

describe("toOpaqueHex", () => {
  it("flattens alpha text tokens over the diagram background", () => {
    expect(toOpaqueHex(parseCssColor("#000000e5")!, WHITE)).toBe("#1a1a1a");
    expect(toOpaqueHex(parseCssColor("#fffffff2")!, BLACK)).toBe("#f2f2f2");
    expect(toOpaqueHex(parseCssColor("rgb(40 109 248 / 50%)")!, WHITE)).toBe(
      "#94b6fc"
    );
  });
});

describe("buildMermaidTheme", () => {
  const lightTokens = {
    "--background-tint-00": "#ffffff",
    "--text-05": "#000000e5",
    "--border-03": "rgb(163, 163, 163)",
  };

  it("maps tokens to themeVariables and omits unresolved tokens", () => {
    const theme = buildMermaidTheme(reader(lightTokens), {
      darkMode: false,
      fontFamily: "Hanken Grotesk",
    });

    expect(theme.themeVariables).toMatchObject({
      darkMode: false,
      fontFamily: "Hanken Grotesk",
      background: "#ffffff",
      primaryTextColor: "#1a1a1a",
      primaryBorderColor: "#a3a3a3",
    });
    expect(theme.themeVariables).not.toHaveProperty("primaryColor");
    expect(Object.keys(MERMAID_THEME_TOKENS)).toContain("lineColor");
  });

  it("derives a different cache key for dark mode and the same key for the same inputs", () => {
    const options = { darkMode: false, fontFamily: "Hanken Grotesk" };
    const light = buildMermaidTheme(reader(lightTokens), options);
    const again = buildMermaidTheme(reader(lightTokens), options);
    const dark = buildMermaidTheme(
      reader({ "--background-tint-00": "#000000", "--text-05": "#fffffff2" }),
      { darkMode: true, fontFamily: "Hanken Grotesk" }
    );

    expect(again.key).toBe(light.key);
    expect(dark.key).not.toBe(light.key);
    expect(dark.themeVariables.primaryTextColor).toBe("#f2f2f2");
  });
});
