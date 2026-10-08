import { render, screen } from "@testing-library/react";
import i18next from "i18next";
import { I18nextProvider, initReactI18next } from "react-i18next";

import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";
import { PerUserAuthConfig } from "@/sections/actions/PerUserAuthConfig";

const values = {
  auth_template: {
    headers: { Authorization: "Bearer {api_key}" },
    required_fields: ["api_key"],
  },
  user_credentials: {},
} as never;

async function renderIn(lng: "en" | "tr") {
  const i18n = i18next.createInstance();
  await i18n.use(initReactI18next).init({
    lng,
    fallbackLng: false,
    resources: {
      en: { translation: en },
      tr: { translation: tr },
    },
    interpolation: { escapeValue: false },
  });
  return render(
    <I18nextProvider i18n={i18n}>
      <PerUserAuthConfig values={values} setFieldValue={jest.fn()} />
    </I18nextProvider>
  );
}

it("renders the header help, placeholder and credentials note in Turkish", async () => {
  const { container } = await renderIn("tr");

  expect(container.textContent).toContain("yer tutucular kullanın");
  expect(container.textContent).toContain("{api_key}");
  expect(container.textContent).not.toContain("Format headers");
  // The note ends at its own sentence; no stray English suffix.
  expect(container.textContent).not.toContain("organization.");
  expect(screen.getByPlaceholderText("api key girin")).toBeInTheDocument();
});

it("renders the same strings in English", async () => {
  const { container } = await renderIn("en");

  expect(container.textContent).toContain("Format headers for each user");
  expect(screen.getByPlaceholderText("Enter api key")).toBeInTheDocument();
});
