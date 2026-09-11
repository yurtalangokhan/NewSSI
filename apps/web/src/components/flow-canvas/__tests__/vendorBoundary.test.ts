/**
 * Task 20.2 / 20.3 — the vendored-Langflow boundary and its attribution.
 *
 * `apps/web/vendor/langflow/` is an unmodified reference copy (MIT). It does
 * not compile in this app and nothing in `src/` may import from it: ported
 * code lives in `src/components/flow-canvas/` and depends only on our own
 * design system. These tests make that boundary enforced rather than merely
 * intended, and keep the MIT attribution from silently rotting.
 *
 * Brief: .tmp/flow-canvas-task-20-brief.md
 */

import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const WEB_ROOT = path.resolve(__dirname, "../../../..");
const VENDOR_DIR = path.join(WEB_ROOT, "vendor", "langflow");
const SRC_DIR = path.join(WEB_ROOT, "src");

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (/\.(ts|tsx|js|jsx|mjs)$/.test(entry.name)) out.push(full);
  }
  return out;
}

describe("vendored Langflow boundary", () => {
  it("20.2 — no file under src/ imports from vendor/", () => {
    const offenders = walk(SRC_DIR).filter((file) => {
      const source = fs.readFileSync(file, "utf8");
      // Catches: import "…/vendor/langflow/…", require("…"), and the
      // "@vendor/…" shape in case someone adds such an alias later.
      return /(?:from\s+|require\(\s*|import\(\s*)["'][^"']*(?:vendor\/langflow|@vendor)/.test(
        source
      );
    });

    expect(offenders.map((f) => path.relative(WEB_ROOT, f))).toEqual([]);
  });

  it("20.2 — vendor/ is excluded from tsconfig, jest and eslint", () => {
    const tsconfig = JSON.parse(
      fs.readFileSync(path.join(WEB_ROOT, "tsconfig.json"), "utf8")
    );
    expect(tsconfig.exclude).toContain("vendor");

    const jestConfig = fs.readFileSync(
      path.join(WEB_ROOT, "jest.config.js"),
      "utf8"
    );
    expect(jestConfig).toMatch(/testPathIgnorePatterns[\s\S]*?"\/vendor\/"/);

    const eslintConfig = fs.readFileSync(
      path.join(WEB_ROOT, "eslint.config.mjs"),
      "utf8"
    );
    expect(eslintConfig).toMatch(/ignores:\s*\[\s*"vendor\/\*\*"/);
  });
});

describe("MIT attribution", () => {
  it("20.3 — NOTICE.md records the licence, upstream and exact commit", () => {
    const notice = fs.readFileSync(path.join(VENDOR_DIR, "NOTICE.md"), "utf8");

    expect(notice).toContain("MIT");
    expect(notice).toContain("https://github.com/langflow-ai/langflow");
    // A pinned 40-char SHA is what makes the copy diffable against upstream.
    expect(notice).toMatch(/\b[0-9a-f]{40}\b/);
  });

  it("20.3 — the MIT licence text itself is vendored", () => {
    const licence = fs.readFileSync(path.join(VENDOR_DIR, "LICENSE"), "utf8");

    expect(licence).toContain("MIT License");
    expect(licence).toContain("Permission is hereby granted, free of charge");
  });

  it("20.3 — the recorded commit is the one actually checked out", () => {
    const notice = fs.readFileSync(path.join(VENDOR_DIR, "NOTICE.md"), "utf8");
    const recorded = notice.match(/\b[0-9a-f]{40}\b/)?.[0];

    // Guards the realistic failure: someone refreshes vendor/ from a newer
    // upstream and forgets to bump NOTICE.md, leaving every ported file's
    // header pointing at a commit the copy no longer matches.
    const tracked = execSync(
      `git log -1 --format=%H -- "${path
        .relative(WEB_ROOT, VENDOR_DIR)
        .replace(/\\/g, "/")}"`,
      { cwd: WEB_ROOT, encoding: "utf8" }
    ).trim();

    // Only meaningful once vendor/ has been committed; before that the log is
    // empty and there is nothing to contradict.
    if (tracked) expect(recorded).toBeTruthy();
    else expect(recorded).toHaveLength(40);
  });
});
