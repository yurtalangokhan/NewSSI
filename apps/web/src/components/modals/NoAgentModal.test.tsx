import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import NoAgentModal from "@/components/modals/NoAgentModal";
import en from "@/i18n/locales/en";
import tr from "@/i18n/locales/tr";

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({ isAdmin: false }),
}));

async function mount(
  language: string,
  catalogError = false,
  onRetry = jest.fn()
) {
  const i18n = createInstance();
  await i18n.init({
    lng: language,
    resources: { en: { common: en }, tr: { common: tr } },
  });
  return render(
    <I18nextProvider i18n={i18n}>
      <NoAgentModal catalogError={catalogError} onRetry={onRetry} />
    </I18nextProvider>
  );
}

test.each([
  ["en", "Unable to load agents", "Retry"],
  ["tr", "Ajanlar yüklenemedi", "Yeniden dene"],
])("shows a localized catalog error in %s", async (language, title, retry) => {
  await mount(language, true);
  expect(screen.getByText(title)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: retry })).toBeInTheDocument();
  expect(screen.queryByText(en.modals.noAgent.title)).not.toBeInTheDocument();
});

test("keeps configuration guidance for a successful empty catalog", async () => {
  await mount("en");
  expect(screen.getByText(en.modals.noAgent.title)).toBeInTheDocument();
  expect(
    screen.getByText(en.modals.noAgent.contactAdminMessage)
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Retry" })
  ).not.toBeInTheDocument();
});

test("retries once, disables while pending, and recovers from another failure", async () => {
  let reject!: (reason: Error) => void;
  const retry = jest.fn(
    () =>
      new Promise<void>((_, fail) => {
        reject = fail;
      })
  );
  await mount("en", true, retry);
  const button = screen.getByRole("button", { name: "Retry" });
  await userEvent.click(button);
  expect(retry).toHaveBeenCalledTimes(1);
  expect(button).toBeDisabled();
  await act(async () => reject(new Error("Still unavailable")));
  await waitFor(() => expect(button).toBeEnabled());
  expect(screen.getByText("Unable to load agents")).toBeInTheDocument();
});
