import { render, screen } from "@testing-library/react";
import OAuthCallbackPage from "./OAuthCallbackPage";
const searchParams = new URLSearchParams({ code: "code", state: "state" });
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
  useSearchParams: () => searchParams,
}));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
jest.mock("@/components/admin/CardSection", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <section>{children}</section>
  ),
}));

it("displays the backend's localized error envelope after an OAuth failure", async () => {
  const callback = jest.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        error: {
          code: "dependency.authentication_failed",
          message:
            "Dış servise bağlanmak için kullanılan kimlik bilgileri reddedildi.",
          details: {},
          field_errors: [],
          request_id: "req-oauth",
        },
      }),
      { status: 502, headers: { "content-type": "application/json" } }
    )
  );
  const config = { callback };
  const log = jest.spyOn(console, "error").mockImplementation(() => {});
  try {
    render(<OAuthCallbackPage config={config} />);
    expect(
      await screen.findByText(
        "Dış servise bağlanmak için kullanılan kimlik bilgileri reddedildi."
      )
    ).toBeInTheDocument();
    expect(callback).toHaveBeenCalledWith("code", "state");
  } finally {
    log.mockRestore();
  }
});
