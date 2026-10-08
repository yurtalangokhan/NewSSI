import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";
import * as icons from "@/icons";

type Tree = { [key: string]: string | Tree };

function leafKeys(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "string"
      ? [`${prefix}${key}`]
      : leafKeys(value, `${prefix}${key}.`)
  );
}

describe.each(["documentPanel", "documentCard", "documentProgress"] as const)(
  "%s translations",
  (ns) => {
    it("has the same keys in en and tr", () => {
      const enKeys = leafKeys(
        (en as unknown as Record<string, Tree>)[ns]!
      ).sort();
      const trKeys = leafKeys(
        (tr as unknown as Record<string, Tree>)[ns]!
      ).sort();
      expect(enKeys.length).toBeGreaterThan(0);
      expect(trKeys).toEqual(enKeys);
    });
  }
);

it("uses the approved Turkish copy", () => {
  expect(tr.documentPanel.tabs.preview).toBe("Önizleme");
  expect(tr.documentPanel.oldRevision.continue).toBe("Bu taslaktan devam et");
  expect(tr.documentPanel.conflict.applyOnLatest).toBe(
    "Taslak {{head}} üzerine uygula"
  );
  expect(tr.documentPanel.contextChip).toBe(
    "Bağlam: {{title}} · Taslak {{revision}}"
  );
  expect(tr.documentProgress.title).toBe("Taslak {{revision}} hazırlanıyor");
});

it("re-exports the panel icons", () => {
  for (const name of [
    "SvgArrowExchange",
    "SvgChevronLeft",
    "SvgChevronRight",
    "SvgClock",
    "SvgFileText",
    "SvgHistory",
    "SvgSparkle",
    "SvgUser",
  ]) {
    expect((icons as Record<string, unknown>)[name]).toBeDefined();
  }
});
