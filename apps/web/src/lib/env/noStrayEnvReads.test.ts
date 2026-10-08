import { readFileSync, readdirSync } from "fs";
import { join, relative } from "path";

const SRC_ROOT = join(__dirname, "../..");

/**
 * Files allowed to name `process.env` directly.
 *
 * `lib/env/index.ts` is the one place that reads it — Next.js only inlines a
 * `NEXT_PUBLIC_` variable it can see spelled out, so `experimental__runtimeEnv`
 * has to list them literally. `instrumentation.ts` reads NEXT_RUNTIME, which is
 * a marker Next.js sets on the bootstrap hook rather than app configuration.
 */
const ALLOWED = new Set(["lib/env/index.ts", "instrumentation.ts"]);

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    if (!/\.tsx?$/.test(entry.name)) return [];
    if (/\.test\.tsx?$/.test(entry.name)) return [];
    return [path];
  });
}

describe("environment access", () => {
  it("reaches the validated env object only through lib/settings", () => {
    const offenders = sourceFiles(SRC_ROOT)
      .filter((path) => /from "@\/lib\/env"/.test(readFileSync(path, "utf8")))
      .map((path) => relative(SRC_ROOT, path))
      .filter((path) => path !== "lib/settings.ts")
      .sort();

    expect(offenders).toEqual([]);
  });

  it("is confined to the central env module", () => {
    const offenders = sourceFiles(SRC_ROOT)
      .filter((path) => readFileSync(path, "utf8").includes("process.env"))
      .map((path) => relative(SRC_ROOT, path))
      .filter((path) => !ALLOWED.has(path))
      .sort();

    expect(offenders).toEqual([]);
  });
});
