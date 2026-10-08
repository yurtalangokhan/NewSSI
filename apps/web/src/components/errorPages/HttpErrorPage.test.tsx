/**
 * @jest-environment jsdom
 */

import { fireEvent, render, screen } from "@tests/setup/test-utils";
import HttpErrorPage from "@/components/errorPages/HttpErrorPage";
import { logout } from "@/lib/api/domains/session/api";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      key === "errors.errorPages.logOutButton" ? "Log out" : key,
  }),
}));
jest.mock("@/components/errorPages/ErrorPageLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
jest.mock("@/lib/api/domains/session/api", () => ({
  logout: jest.fn().mockResolvedValue(undefined),
}));

it("lets a user log out from the 403 page", () => {
  render(<HttpErrorPage code={403} />);

  fireEvent.click(screen.getByRole("button", { name: "Log out" }));

  expect(logout).toHaveBeenCalledTimes(1);
});

it("does not show logout on unrelated HTTP errors", () => {
  render(<HttpErrorPage code={404} />);

  expect(
    screen.queryByRole("button", { name: "Log out" })
  ).not.toBeInTheDocument();
});
