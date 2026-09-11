import { screen } from "@testing-library/react";

import MailConfigsPage from "@/app/admin/configuration/mail-configs/page";
import {
  deleteMailConfig,
  testMailConfig,
  useMailConfigs,
} from "@/lib/mailConfigs";
import { render, setupUser } from "@tests/setup/test-utils";

jest.mock("@/lib/mailConfigs", () => ({
  createMailConfig: jest.fn(),
  deleteMailConfig: jest.fn(),
  testMailConfig: jest.fn(),
  updateMailConfig: jest.fn(),
  useMailConfigs: jest.fn(),
}));

jest.mock("react-i18next", () => ({
  useTranslation: (_namespace?: string, options?: { keyPrefix?: string }) => ({
    t: (key: string) =>
      options?.keyPrefix ? `${options.keyPrefix}.${key}` : key,
  }),
}));

const mockedUseMailConfigs = jest.mocked(useMailConfigs);
const mockedDeleteMailConfig = jest.mocked(deleteMailConfig);
const mockedTestMailConfig = jest.mocked(testMailConfig);

describe("MailConfigsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedUseMailConfigs.mockReturnValue({
      mailConfigs: [
        {
          id: "config-1",
          name: "Corporate SMTP",
          host: "smtp.example.com",
          port: 587,
          username: "sender@example.com",
          from_email: "sender@example.com",
          from_name: "Sender",
          security: "starttls",
          is_active: true,
          password_configured: true,
          last_tested_at: null,
          time_created: null,
          time_updated: null,
        },
      ],
      totalItems: 1,
      totalPages: 1,
      currentPage: 1,
      error: undefined,
      isLoading: false,
      refreshMailConfigs: jest.fn(),
    });
    mockedDeleteMailConfig.mockResolvedValue(undefined);
    mockedTestMailConfig.mockResolvedValue({ success: true, message: "sent" });
  });

  it("requires confirmation before deleting a mail configuration", async () => {
    const user = setupUser();
    render(<MailConfigsPage />);

    // The row's Delete only opens the confirmation modal.
    await user.click(
      screen.getByRole("button", {
        name: "admin.mailConfigs.deleteButton",
      })
    );

    expect(mockedDeleteMailConfig).not.toHaveBeenCalled();
    expect(
      screen.getByText("admin.mailConfigs.deleteConfirmTitle")
    ).toBeInTheDocument();

    // Confirming inside the modal is what deletes.
    const confirmButtons = screen.getAllByRole("button", {
      name: "admin.mailConfigs.deleteButton",
    });
    await user.click(confirmButtons[confirmButtons.length - 1]!);

    expect(mockedDeleteMailConfig).toHaveBeenCalledWith("config-1");
  });

  it("tests a configuration using its saved sender email", async () => {
    const user = setupUser();
    render(<MailConfigsPage />);

    await user.click(
      screen.getByRole("button", { name: "admin.mailConfigs.testButton" })
    );

    expect(mockedTestMailConfig).toHaveBeenCalledWith(
      "config-1",
      "sender@example.com"
    );
  });

  it("says it is loading while mail configurations load", () => {
    mockedUseMailConfigs.mockReturnValue({
      mailConfigs: [],
      totalItems: 0,
      totalPages: 1,
      currentPage: 1,
      error: undefined,
      isLoading: true,
      refreshMailConfigs: jest.fn(),
    });

    render(<MailConfigsPage />);

    expect(
      screen.getByText("admin.mailConfigs.loadingAccounts")
    ).toBeInTheDocument();
    expect(
      screen.queryByText("admin.mailConfigs.noConfigsYet")
    ).not.toBeInTheDocument();
  });
});
