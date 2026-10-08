import { screen, waitFor } from "@testing-library/react";

import UserRoleDropdown from "@/components/admin/users/buttons/UserRoleDropdown";
import { setDirectoryUserRole } from "@/lib/api/domains/access/api";
import { type User } from "@/lib/types";
import { render, setupUser } from "@tests/setup/test-utils";

const enduserId = "11111111-1111-4111-8111-111111111111";
const auditorId = "22222222-2222-4222-8222-222222222222";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, options?: { defaultValue?: string }) =>
      options?.defaultValue ?? _key,
  }),
}));
jest.mock("@/lib/api/domains/access/api", () => ({
  setDirectoryUserRole: jest.fn(),
}));
jest.mock("@/lib/api/domains/access/hooks", () => ({
  useDirectoryRoles: () => ({
    data: {
      roles: [
        { id: enduserId, name: "enduser", description: null, is_builtin: true },
        {
          id: auditorId,
          name: "auditor",
          description: null,
          is_builtin: false,
        },
      ],
    },
    isLoading: false,
  }),
}));
jest.mock("swr/mutation", () => ({
  __esModule: true,
  default: (key: string, fetcher: Function) => ({
    isMutating: false,
    trigger: (arg: unknown) => fetcher(key, { arg }),
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

const user = { id: "u-1", email: "u@example.com", role: "enduser" } as User;

beforeEach(() => {
  jest.mocked(setDirectoryUserRole).mockResolvedValue({
    ...user,
    role: "auditor",
  } as User);
});

test("shows the user's current role by its Keycloak role ID", () => {
  render(
    <UserRoleDropdown user={user} onSuccess={jest.fn()} onError={jest.fn()} />
  );

  expect(screen.getByLabelText("role")).toHaveValue(enduserId);
});

test("changes the role by posting the selected Keycloak role ID", async () => {
  const onSuccess = jest.fn();
  render(
    <UserRoleDropdown user={user} onSuccess={onSuccess} onError={jest.fn()} />
  );

  await setupUser().selectOptions(screen.getByLabelText("role"), auditorId);

  await waitFor(() =>
    expect(setDirectoryUserRole).toHaveBeenCalledWith("u-1", auditorId)
  );
  expect(onSuccess).toHaveBeenCalledWith({ ...user, role: "auditor" });
});
