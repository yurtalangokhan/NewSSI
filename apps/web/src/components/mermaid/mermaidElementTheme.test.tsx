import { readElementTheme } from "@/components/mermaid/mermaidTheme";

/**
 * `readElementTheme` needs a real DOM (jsdom), which is why it lives in a
 * `.tsx` test rather than beside the pure colour maths in mermaidTheme.test.ts.
 */
const lightTokens: Record<string, string> = {
  "--background-tint-00": "#ffffff",
  "--background-tint-02": "#f0f0f1",
  "--text-05": "#000000e5",
};

function mockStyles(tokens: Record<string, string>) {
  return jest.spyOn(window, "getComputedStyle").mockReturnValue({
    getPropertyValue: (token: string) => tokens[token] ?? "",
    fontFamily: "",
  } as unknown as CSSStyleDeclaration);
}

afterEach(() => {
  document.documentElement.classList.remove("dark");
  document.body.innerHTML = "";
  jest.restoreAllMocks();
});

it("reads the surface tokens and drops dark mode inside a light scope", () => {
  document.documentElement.classList.add("dark");
  const scope = document.createElement("div");
  scope.className = "theme-light";
  const element = document.createElement("div");
  scope.appendChild(element);
  document.body.appendChild(scope);
  mockStyles(lightTokens);

  const theme = readElementTheme(element);

  // The document panel's white page must not render dark-mode diagrams.
  expect(theme.darkMode).toBe(false);
  expect(theme.themeVariables.background).toBe("#ffffff");
  expect(theme.themeVariables.primaryColor).toBe("#f0f0f1");
});

it("keeps dark mode outside a light scope", () => {
  document.documentElement.classList.add("dark");
  const element = document.createElement("div");
  document.body.appendChild(element);
  mockStyles({ "--background-tint-00": "#000000" });

  const theme = readElementTheme(element);

  expect(theme.darkMode).toBe(true);
  expect(theme.themeVariables.background).toBe("#000000");
});

it("falls back to the document theme without an element", () => {
  document.documentElement.classList.add("dark");

  expect(readElementTheme(null).darkMode).toBe(true);
});
