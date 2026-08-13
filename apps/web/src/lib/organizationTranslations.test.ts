import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";

function leafKeys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) return [prefix];

  return Object.entries(value).flatMap(([key, child]) =>
    leafKeys(child, prefix ? `${prefix}.${key}` : key)
  );
}

describe("organization translations", () => {
  it("provides matching English and Turkish organization translation keys", () => {
    const english = en.admin.organizations;
    const turkish = tr.admin.organizations;

    expect(english).toBeDefined();
    expect(turkish).toBeDefined();
    expect(leafKeys(turkish)).toEqual(leafKeys(english));
  });

  it("includes localized labels for the tree, designer, users, and access panels", () => {
    const english = en.admin.organizations;
    const turkish = tr.admin.organizations;

    expect(english.tree.title).toBe("Organization");
    expect(turkish.tree.title).toBe("Organizasyon");
    expect(turkish.designer.title).toBe("Organizasyon tasarımcısı");
    expect(turkish.users.title).toBe("Üyeler");
    expect(turkish.access.unitAccess).toBe("Birim erişimi");
  });

  it("describes child organizations as alt birim in Turkish", () => {
    expect(tr.admin.organizations.designer.childCount_one).toBe(
      "{{count}} alt birim"
    );
    expect(tr.admin.organizations.designer.childCount_other).toBe(
      "{{count}} alt birim"
    );
  });
});
