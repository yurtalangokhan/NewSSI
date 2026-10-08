import { readdirSync, readFileSync } from "fs";
import { join } from "path";

/**
 * A top-level `import … "mermaid"` or `export … from "mermaid"` would
 * execute (or re-export and thus force bundling of) Mermaid during SSR.
 */
const STATIC_MERMAID_IMPORT =
  /^\s*(?:import|export)\b[^;]*?\bfrom\s*["']mermaid["']/m;

/** Referencing a `mock`-prefixed variable inside the factory is allowed
 * through jest's module-factory hoisting, so this still counts calls even
 * though `jest.mock` itself runs before the rest of the file. */
const mockMermaidFactory = jest.fn(() => {
  throw new Error("mermaid must not load in this environment");
});
jest.mock("mermaid", () => mockMermaidFactory());

describe("mermaid stays client-only", () => {
  it("never imports or re-exports mermaid statically", () => {
    const offenders = readdirSync(__dirname)
      .filter((file) => /\.(ts|tsx)$/.test(file) && !/\.test\.tsx?$/.test(file))
      .filter((file) =>
        STATIC_MERMAID_IMPORT.test(readFileSync(join(__dirname, file), "utf8"))
      );

    expect(offenders).toEqual([]);
  });

  it("imports and creates the runtime in a DOM-less environment without loading mermaid", async () => {
    expect(typeof window).toBe("undefined");
    const runtimeModule = await import("@/components/mermaid/mermaidRuntime");
    const runtime = runtimeModule.getMermaidRuntime();

    expect(typeof runtime.render).toBe("function");
    // If mermaid had been imported eagerly (module load or singleton
    // construction), the mocked factory above would already have thrown.
    expect(mockMermaidFactory).not.toHaveBeenCalled();

    // Only the first real render attempts to load mermaid, proving the
    // import is genuinely deferred rather than simply unused in this file.
    await expect(
      runtime.render("A", {
        key: "test",
        darkMode: false,
        fontFamily: "sans-serif",
        themeVariables: {},
      })
    ).rejects.toThrow("mermaid must not load in this environment");
    expect(mockMermaidFactory).toHaveBeenCalledTimes(1);
  });
});
