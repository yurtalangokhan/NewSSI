import { createInstance } from "i18next";
import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";

it.each(["Unit Manager", "unit-manager", "unit_manager", "unitmanager"])(
  "translates stored role %s in the selected language",
  async (role) => {
    const i18n = createInstance();
    await i18n.init({
      lng: "tr",
      resources: { en: { translation: en }, tr: { translation: tr } },
    });
    expect(i18n.t(`admin.users.roles.${role}`, { defaultValue: role })).toBe(
      "Birim Yöneticisi"
    );
    await i18n.changeLanguage("en");
    expect(i18n.t(`admin.users.roles.${role}`, { defaultValue: role })).toBe(
      "Unit Manager"
    );
  }
);
