import { fenceCode } from "@/sections/document-panel/fence";

describe("fenceCode", () => {
  it("uses three backticks for a plain body", () => {
    expect(fenceCode("a = 1", "python")).toBe("```python\na = 1\n```");
  });

  it("omits the language for an empty one", () => {
    expect(fenceCode("x", "")).toBe("```\nx\n```");
  });

  it("uses a fence longer than the longest backtick run in the body", () => {
    const body = "before\n```js\ninner\n```\nafter";
    expect(fenceCode(body, "md")).toBe(`\`\`\`\`md\n${body}\n\`\`\`\``);
  });

  it("also outgrows inline runs of four backticks", () => {
    expect(fenceCode("use ```` here", "")).toMatch(/^`{5}\n/);
  });
});
