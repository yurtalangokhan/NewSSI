import { readFileSync } from "fs";
import { resolve } from "path";

const pkg = JSON.parse(
  readFileSync(resolve(__dirname, "../../../package.json"), "utf8")
) as {
  dependencies: Record<string, string>;
  devDependencies: Record<string, string>;
};

describe("document panel dependencies", () => {
  it.each([
    ["react-resizable-panels", "4.14.1"],
    ["@codemirror/view", "6.43.13"],
    ["@codemirror/state", "6.7.6"],
    ["@codemirror/commands", "6.11.1"],
    ["@codemirror/lang-markdown", "6.5.2"],
    ["@codemirror/merge", "6.12.2"],
    ["unified", "11.0.5"],
    ["remark-parse", "11.0.0"],
    ["remark-gfm", "4.0.1"],
    ["mdast-util-to-string", "4.0.0"],
  ])("pins %s to %s", (name, version) => {
    expect(pkg.dependencies[name]).toBe(version);
  });

  it("types mdast for the diff engine", () => {
    expect(pkg.devDependencies["@types/mdast"]).toBe("4.0.4");
  });

  it("keeps jsdiff on the 5.x line the engine is written against", () => {
    expect(pkg.dependencies.diff).toMatch(/^\^?5\./);
  });
});
