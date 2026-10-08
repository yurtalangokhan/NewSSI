import { screen } from "@testing-library/react";

import EmailSettingsPage from "@/app/app/settings/email/page";
import { render, setupUser } from "@tests/setup/test-utils";
import {
  deleteUserMailSettings,
  saveUserMailSettings,
} from "@/lib/api/domains/system/api";
import {
  useAvailableMailConfigs,
  useUserMailSettings,
} from "@/lib/api/domains/system/hooks";

jest.mock("@/lib/api/domains/system/api", () => ({
  deleteUserMailSettings: jest.fn(),
  saveUserMailSettings: jest.fn(),
  testUserMailSettings: jest.fn(),
}));
jest.mock("@/lib/api/domains/system/hooks", () => ({
  useAvailableMailConfigs: jest.fn(),
  useUserMailSettings: jest.fn(),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { entityName?: string }) =>
      options?.entityName ? `${key} ${options.entityName}` : key,
  }),
}));

// Each case drives ~40 keystrokes through userEvent, and every one of them
// re-renders the form inside act(). That lands close enough to Jest's 5s
// default that the suite tips over whenever the machine is busy -- with
// `maxWorkers: "50%"` the first case times out, and a timed-out case skips
// testing-library's cleanup, so the three after it query an empty
// `<body><div /></body>` and fail for reasons that have nothing to do with
// them. The budget is per test, so raising it costs nothing when they pass.
jest.setTimeout(30_000);

const mockedUseUserMailSettings = jest.mocked(useUserMailSettings);
const mockedUseAvailableMailConfigs = jest.mocked(useAvailableMailConfigs);
const mockedSaveUserMailSettings = jest.mocked(saveUserMailSettings);
const mockedDeleteUserMailSettings = jest.mocked(deleteUserMailSettings);

describe("EmailSettingsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedUseUserMailSettings.mockReturnValue({
      userMailSettings: null,
      refreshUserMailSettings: jest.fn(),
      isLoading: false,
      error: undefined,
    });
    mockedUseAvailableMailConfigs.mockReturnValue({
      availableMailConfigs: [
        {
          id: "config-1",
          name: "Corporate SMTP",
          host: "smtp.example.com",
          port: 587,
          security: "starttls",
        },
      ],
      isLoading: false,
      error: undefined,
    });
  });

  it("saves personal SMTP credentials from the dedicated page", async () => {
    const user = setupUser();
    render(<EmailSettingsPage />);

    await user.type(
      screen.getByPlaceholderText("settings.accounts.emailUsernamePlaceholder"),
      "mail-user"
    );
    await user.type(
      screen.getByPlaceholderText("settings.accounts.emailPasswordPlaceholder"),
      "secret"
    );
    await user.type(
      screen.getByPlaceholderText("user@example.com"),
      "me@example.com"
    );
    await user.type(screen.getByPlaceholderText("John Doe"), "Example User");
    await user.click(
      screen.getByRole("button", {
        name: "settings.accounts.saveEmailButton",
      })
    );

    expect(mockedSaveUserMailSettings).toHaveBeenCalledWith({
      mail_config_id: "config-1",
      username: "mail-user",
      password: "secret",
      from_email: "me@example.com",
      from_name: "Example User",
    });
  });

  it("requires confirmation before deleting personal email settings", async () => {
    const refreshUserMailSettings = jest.fn();
    mockedUseUserMailSettings.mockReturnValue({
      userMailSettings: {
        mail_config_id: "config-1",
        username: "mail-user",
        from_email: "me@example.com",
        from_name: "Example User",
        password_configured: true,
        is_active: true,
        last_tested_at: null,
        time_created: null,
        time_updated: null,
      },
      refreshUserMailSettings,
      isLoading: false,
      error: undefined,
    });
    mockedDeleteUserMailSettings.mockResolvedValue(undefined);
    const user = setupUser();
    render(<EmailSettingsPage />);

    await user.click(
      screen.getByRole("button", {
        name: "settings.accounts.removeEmailConfigButton",
      })
    );

    expect(mockedDeleteUserMailSettings).not.toHaveBeenCalled();
    expect(
      screen.getByText("modals.confirmEntity.confirmation me@example.com")
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "modals.cancel" }));
    expect(mockedDeleteUserMailSettings).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: "modals.delete" })
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", {
        name: "settings.accounts.removeEmailConfigButton",
      })
    );

    await user.click(screen.getByRole("button", { name: "modals.delete" }));

    expect(mockedDeleteUserMailSettings).toHaveBeenCalledTimes(1);
  });

  it("requires an explicit mail configuration selection when multiple are available", () => {
    mockedUseAvailableMailConfigs.mockReturnValue({
      availableMailConfigs: [
        {
          id: "config-1",
          name: "Primary SMTP",
          host: "smtp-1.example.com",
          port: 587,
          security: "starttls",
        },
        {
          id: "config-2",
          name: "Backup SMTP",
          host: "smtp-2.example.com",
          port: 465,
          security: "ssl",
        },
      ],
      isLoading: false,
      error: undefined,
    });

    render(<EmailSettingsPage />);

    expect(
      screen.getByText("settings.accounts.mailConfigLabel")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "settings.accounts.saveEmailButton",
      })
    ).toBeDisabled();
  });

  it("shows a non-blocking loader and prevents premature saves while settings load", async () => {
    mockedUseUserMailSettings.mockReturnValue({
      userMailSettings: null,
      refreshUserMailSettings: jest.fn(),
      isLoading: true,
      error: undefined,
    });

    const user = setupUser();
    render(<EmailSettingsPage />);

    expect(screen.getByLabelText("grid-loading")).toBeInTheDocument();
    expect(
      screen.getByText("settings.accounts.emailUsernameLabel")
    ).toBeInTheDocument();

    await user.type(
      screen.getByPlaceholderText("settings.accounts.emailUsernamePlaceholder"),
      "mail-user"
    );
    await user.type(
      screen.getByPlaceholderText("settings.accounts.emailPasswordPlaceholder"),
      "secret"
    );
    await user.type(
      screen.getByPlaceholderText("user@example.com"),
      "me@example.com"
    );

    expect(
      screen.getByRole("button", {
        name: "settings.accounts.saveEmailButton",
      })
    ).toBeDisabled();
  });
});
