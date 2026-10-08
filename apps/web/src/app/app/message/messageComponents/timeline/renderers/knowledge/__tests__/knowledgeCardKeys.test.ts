import { readdirSync, readFileSync } from "fs";
import { join } from "path";
import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";

const SRC = join(process.cwd(), "src");
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      return entry.name === "i18n" || entry.name === "__tests__"
        ? []
        : sourceFiles(path);
    }
    return /\.(ts|tsx)$/.test(entry.name) && !/\.test\./.test(entry.name)
      ? [path]
      : [];
  });
}

describe("knowledgeCard translations", () => {
  const source = sourceFiles(SRC)
    .map((path) => readFileSync(path, "utf8"))
    .join("\n");

  it.each([
    ["en", en.knowledgeCard],
    ["tr", tr.knowledgeCard],
  ])("has no key in %s that nothing reads", (_locale, block) => {
    const unused = Object.keys(block).filter(
      (key) =>
        !source.includes(`knowledgeCard.${key.replace(PLURAL_SUFFIX, "")}`)
    );

    expect(unused).toEqual([]);
  });
});
