import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";

function leafKeys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) return [prefix];
  return Object.entries(value).flatMap(([key, child]) =>
    leafKeys(child, prefix ? `${prefix}.${key}` : key)
  );
}

describe("mermaid translations", () => {
  it("has the same keys in English and Turkish", () => {
    expect(leafKeys(tr.mermaid).sort()).toEqual(leafKeys(en.mermaid).sort());
  });

  it("uses the approved Turkish copy", () => {
    expect(tr.mermaid.showDiagram).toBe("Diyagram");
    expect(tr.mermaid.showCode).toBe("Kod");
    expect(tr.mermaid.copyCode).toBe("Kodu kopyala");
    expect(tr.mermaid.askAgentToFix).toBe("Ajana düzelttir");
    expect(tr.mermaid.types.sequence).toBe("sıra diyagramı");
    expect(tr.mermaid.writing_other).toBe(
      "Diyagram yazılıyor · {{count}} satır"
    );
  });

  it("keeps the fix request a fenced mermaid block in both languages", () => {
    for (const locale of [en, tr]) {
      expect(locale.mermaid.fixRequest).toContain(
        "```mermaid\n{{source}}\n```"
      );
    }
  });
});
