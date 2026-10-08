import { readFileSync } from "fs";
import { resolve } from "path";
import mermaid from "mermaid";

const packageJson = JSON.parse(
  readFileSync(resolve(__dirname, "../../../package.json"), "utf8")
) as { dependencies: Record<string, string> };

describe("mermaid dependency", () => {
  it("pins mermaid to the version bundled in the server validator (mermaidx 0.9.5)", () => {
    expect(packageJson.dependencies.mermaid).toBe("11.16.0");
  });

  it("resolves to the jsdom-safe double under Jest", async () => {
    const result = await mermaid.render("mmd1z", "flowchart LR\n  A --> B");

    expect(result.svg).toContain('id="mmd1z"');
    expect(result.svg).toContain('id="mmd1z_arrow"');
  });

  it("fails like Mermaid's parser on a line containing BROKEN", async () => {
    await expect(
      mermaid.render("mmd2z", "flowchart LR\n  A BROKEN B")
    ).rejects.toThrow("Parse error on line 2:");
  });
});
