import fs from "fs";
import path from "path";
import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";

/**
 * Static guard for a bug class the hardcoded-string linters cannot see:
 * a `t("some.key", "English default")` call whose key does not exist in a
 * locale. The dynamic default masks it at runtime — the UI always renders
 * *something* — so a missing key (or a key pointed at the wrong namespace)
 * silently ships English (or, worse, whatever language the in-code default
 * happens to be) to every other locale.
 *
 * This scans every `t("literal.key", …)` call under `flow-canvas/**` and
 * asserts the key resolves in both `en` and `tr`, honouring i18next's
 * `_one` / `_other` / `_zero` plural and `_<context>` suffixes.
 *
 * Only namespaces owned by the flow feature are checked — widen
 * `CHECKED_NAMESPACES` as other areas adopt the same discipline.
 */

const FLOW_CANVAS_ROOT = path.resolve(
  process.cwd(),
  "src/components/flow-canvas"
);
const CHECKED_NAMESPACES = ["flowCanvas", "flowStudio", "agentViewer"];

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "__tests__") continue;
      out.push(...sourceFiles(full));
    } else if (
      /\.(ts|tsx)$/.test(entry.name) &&
      !/\.(test|stories)\.(ts|tsx)$/.test(entry.name)
    ) {
      out.push(full);
    }
  }
  return out;
}

/** `t("a.b.c", …)` — quoted (static) keys only. Keys built with a template
 * literal (`` t(`ns.${x}`) ``) are dynamic by design and are skipped. i18n
 * keys are `[A-Za-z0-9_.]` only, so a plain char class is enough. */
function collectStaticKeys(): string[] {
  const re = /\bt\(\s*["']([A-Za-z0-9_.]+)["']/g;
  const keys = new Set<string>();
  for (const file of sourceFiles(FLOW_CANVAS_ROOT)) {
    const src = fs.readFileSync(file, "utf8");
    let m: RegExpExecArray | null;
    while ((m = re.exec(src)) !== null) {
      const key = m[1];
      if (!key) continue;
      const namespace = key.split(".")[0];
      if (namespace && CHECKED_NAMESPACES.includes(namespace)) keys.add(key);
    }
  }
  // `Array.from` (a runtime method call) — not `[...keys]`, which this repo's
  // es5 tsconfig target down-levels to a helper that cannot iterate a Set.
  return Array.from(keys).sort();
}

function resolves(bundle: unknown, dotted: string): boolean {
  const segs = dotted.split(".");
  let cur: unknown = bundle;
  for (let i = 0; i < segs.length; i++) {
    if (cur == null || typeof cur !== "object") return false;
    const rec = cur as Record<string, unknown>;
    const seg = segs[i];
    if (seg === undefined) return false;
    if (i === segs.length - 1) {
      if (seg in rec) return true;
      // i18next appends _one/_other/_zero/_two/_few/_many for plurals and
      // _<context> for context — any sibling with that prefix counts.
      return Object.keys(rec).some((k) => k.startsWith(`${seg}_`));
    }
    if (!(seg in rec)) return false;
    cur = rec[seg];
  }
  return true;
}

describe("flow-canvas t() keys resolve in every locale", () => {
  it("scans a non-trivial number of keys (guards against a broken regex)", () => {
    expect(collectStaticKeys().length).toBeGreaterThan(100);
  });

  it("every key exists in en.ts", () => {
    const missing = collectStaticKeys().filter((k) => !resolves(en, k));
    expect(missing).toEqual([]);
  });

  it("every key exists in tr.ts", () => {
    const missing = collectStaticKeys().filter((k) => !resolves(tr, k));
    expect(missing).toEqual([]);
  });
});
