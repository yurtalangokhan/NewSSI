/**
 * 26.11 — the only mechanical guard against a ported shadcn/raw-HTML
 * control slipping through this task's 13 field renderers. A rendered-DOM
 * query can't express this: every `refresh-components` primitive
 * ultimately renders a native `<input>`/`<button>`/`<textarea>` too — the
 * point is that *our* files (fields/, nodes/) never write one directly,
 * only ever compose a `refresh-components`/`@opal` primitive. Same
 * source-scan technique as Task 20's vendorBoundary.test.ts.
 *
 * Brief: .tmp/flow-canvas-task-26-brief.md
 */

import fs from "fs";
import path from "path";

const FORBIDDEN_TAGS = ["<input", "<textarea", "<select", "<button"];
const SCAN_DIRS = ["fields", "nodes"];

function tsxFilesUnder(dir: string): string[] {
  const full = path.join(__dirname, "..", dir);
  if (!fs.existsSync(full)) return [];
  return fs
    .readdirSync(full)
    .filter((f) => f.endsWith(".tsx"))
    .map((f) => path.join(full, f));
}

describe("26.11 — no raw HTML form elements in fields/ or nodes/", () => {
  const files = SCAN_DIRS.flatMap(tsxFilesUnder);

  it("found at least one file to scan (sanity check the scan isn't vacuous)", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it.each(files.map((f) => [path.basename(f), f] as const))(
    "%s contains no raw <input>/<textarea>/<select>/<button>",
    (_name, file) => {
      const source = fs.readFileSync(file, "utf-8");
      for (const tag of FORBIDDEN_TAGS) {
        expect(source).not.toContain(tag);
      }
    }
  );
});
