import { screen, waitFor } from "@testing-library/react";

import AddUserPage from "@/app/admin/users/add/page";
import { createDirectoryUser } from "@/lib/api/domains/access/api";
import { render, setupUser } from "@tests/setup/test-utils";

const enduserId = "11111111-1111-4111-8111-111111111111";
const auditorId = "22222222-2222-4222-8222-222222222222";

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), refresh: jest.fn() }),
}));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) =>
      options?.defaultValue ?? key,
  }),
}));
jest.mock("@/hooks/useToast", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
jest.mock("@/components/admin/AdminOverviewPanel", () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock("@/lib/api/domains/access/api", () => ({
  createDirectoryUser: jest.fn(),
}));
jest.mock("@/lib/api/domains/access/hooks", () => ({
  useDirectoryRoles: () => ({
    data: {
      roles: [
        { id: enduserId, name: "enduser" },
        { id: auditorId, name: "auditor" },
      ],
    },
    isLoading: false,
  }),
}));
jest.mock("@/refresh-components/inputs/InputSelect", () => {
  function InputSelect({
    value,
    onValueChange,
    children,
  }: {
    value: string;
    onValueChange: (value: string) => void;
    children: React.ReactNode;
  }) {
    return (
      <select
        aria-label="role"
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
      >
        <option value="" />
        {children}
      </select>
    );
  }
  InputSelect.Trigger = () => null;
  InputSelect.Content = ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  );
  InputSelect.Item = ({
    value,
    children,
  }: {
    value: string;
    children: React.ReactNode;
  }) => <option value={value}>{children}</option>;
  return { __esModule: true, default: InputSelect };
});

beforeEach(() => {
  jest.mocked(createDirectoryUser).mockResolvedValue({
    ok: true,
    json: async () => ({}),
  } as Response);
});

async function fillRequiredFields() {
  const user = setupUser();
  await user.type(screen.getByPlaceholderText("newuser"), "newuser");
  await user.type(screen.getByPlaceholderText("user@example.com"), "n@x.test");
  await user.type(screen.getByPlaceholderText("John"), "New");
  await user.type(screen.getByPlaceholderText("Doe"), "User");
  await user.type(
    screen.getByPlaceholderText("admin.users.createPasswordPlaceholder"),
    "secret-password"
  );
  return user;
}

function submittedBody() {
  const [payload] = jest.mocked(createDirectoryUser).mock.calls[0]!;
  return payload;
}

test("preselects the enduser role and submits its Keycloak role ID", async () => {
  render(<AddUserPage />);
  const user = await fillRequiredFields();

  expect(screen.getByLabelText("role")).toHaveValue(enduserId);
  await user.click(
    screen.getByRole("button", { name: "admin.users.addUserButton" })
  );

  await waitFor(() => expect(createDirectoryUser).toHaveBeenCalled());
  expect(submittedBody()).toMatchObject({ role_id: enduserId });
  expect(submittedBody()).not.toHaveProperty("role");
});

test("submits the Keycloak role ID of the chosen initial role", async () => {
  render(<AddUserPage />);
  const user = await fillRequiredFields();

  await user.selectOptions(screen.getByLabelText("role"), auditorId);
  await user.click(
    screen.getByRole("button", { name: "admin.users.addUserButton" })
  );

  await waitFor(() => expect(createDirectoryUser).toHaveBeenCalled());
  expect(submittedBody()).toMatchObject({ role_id: auditorId });
});
