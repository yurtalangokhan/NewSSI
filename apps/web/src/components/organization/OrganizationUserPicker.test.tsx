import { fakeResponse } from "@tests/setup/responseModel";
import { screen, waitFor } from "@testing-library/react";
import "@/i18n/config";
import { render, setupUser } from "@tests/setup/test-utils";
import { OrganizationUserPicker } from "./OrganizationUserPicker";

const originalFetch = global.fetch;
afterEach(() => {
  global.fetch = originalFetch;
});

test("searches the server and supports keyboard selection without retaining an edited selection", async () => {
  global.fetch = jest.fn(async (url) =>
    fakeResponse(true, undefined, {
      users: String(url).includes("query=alice")
        ? [{ id: "u1", email: "alice@example.com" }]
        : [],
      total: 1,
    })
  ) as jest.Mock;
  const onSelect = jest.fn();
  const user = setupUser();
  render(
    <OrganizationUserPicker organizationId="search-unit" onSelect={onSelect} />
  );
  const input = screen.getByRole("combobox", { name: "User" });
  await user.type(input, "alice");
  await screen.findByRole("option", { name: "alice@example.com" });
  expect(global.fetch).toHaveBeenCalledWith(
    "/api/user-service/organizations/search-unit/assignable-users?query=alice&limit=20",
    expect.objectContaining({ credentials: "include" })
  );
  await user.keyboard("{ArrowDown}{Enter}");
  expect(onSelect).toHaveBeenLastCalledWith("u1");
  expect(input).toHaveValue("alice@example.com");
  await user.type(input, "x");
  expect(onSelect).toHaveBeenLastCalledWith("");
  expect(
    screen.queryByRole("option", { name: "alice@example.com" })
  ).not.toBeInTheDocument();
});

test("shows a failed search without exposing previous candidates", async () => {
  global.fetch = jest.fn(async () => ({ ok: false })) as jest.Mock;
  const user = setupUser();
  render(
    <OrganizationUserPicker organizationId="failed-unit" onSelect={jest.fn()} />
  );
  await user.click(screen.getByRole("combobox", { name: "User" }));
  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent("Could not load users")
  );
  expect(screen.queryByRole("option")).not.toBeInTheDocument();
});

test("ArrowUp starts at the last result and gives keyboard focus a visible highlight", async () => {
  global.fetch = jest.fn(async () =>
    fakeResponse(true, undefined, {
      users: [
        { id: "a", email: "a@example.com" },
        { id: "b", email: "b@example.com" },
        { id: "c", email: "c@example.com" },
      ],
      total: 3,
    })
  ) as jest.Mock;
  const user = setupUser();
  render(
    <OrganizationUserPicker
      organizationId="keyboard-unit"
      onSelect={jest.fn()}
    />
  );
  await user.click(screen.getByRole("combobox", { name: "User" }));
  const last = await screen.findByRole("option", { name: "c@example.com" });
  await user.keyboard("{ArrowUp}");
  expect(last).toHaveAttribute("aria-selected", "true");
  expect(last).toHaveClass("bg-background-neutral-02");
});
