import { fakeResponse } from "@tests/setup/responseModel";
import { screen, waitFor } from "@testing-library/react";
import { useSWRConfig } from "swr";
import "@/i18n/config";
import { render, setupUser } from "@tests/setup/test-utils";
import { OrganizationSummaryCounts } from "./OrganizationSummaryCounts";

const endpoint = (org: string, type: string) =>
  `/api/user-service/permissions/organizations/${org}/targets/organization/${org}/resources/${type}`;
const originalFetch = global.fetch;
afterEach(() => {
  global.fetch = originalFetch;
});
function SaveFixture() {
  const { mutate } = useSWRConfig();
  return (
    <button
      onClick={() =>
        void mutate(
          endpoint("org-a", "agent"),
          { permissions: [{ resource_id: "a" }], count: 1 },
          { revalidate: false }
        )
      }
    >
      Save access
    </button>
  );
}
test("counts the selected unit's agents and collections and follows saved access", async () => {
  global.fetch = jest.fn(async (url) =>
    fakeResponse(true, undefined, {
      permissions: String(url).endsWith("/agent")
        ? [{ resource_id: "a" }, { resource_id: "a" }, { resource_id: "b" }]
        : [{ resource_id: "c" }],
      count: 99,
    })
  ) as jest.Mock;
  const user = setupUser();
  render(
    <>
      <OrganizationSummaryCounts
        organizationId="org-a"
        activeMembers={10}
        membersLoading={false}
      />
      <SaveFixture />
    </>
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Agents: 2")).toBeInTheDocument()
  );
  expect(screen.getByLabelText("Collections: 1")).toBeInTheDocument();
  expect(screen.getByLabelText("Active members: 10")).toBeInTheDocument();
  expect(global.fetch).toHaveBeenCalledWith(
    endpoint("org-a", "agent"),
    expect.objectContaining({ credentials: "include" })
  );
  expect(global.fetch).toHaveBeenCalledWith(
    endpoint("org-a", "rag_collection"),
    expect.objectContaining({ credentials: "include" })
  );
  await user.click(screen.getByRole("button", { name: "Save access" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Agents: 1")).toBeInTheDocument()
  );
});
test("switches unit queries and shows unavailable instead of zero for errors", async () => {
  global.fetch = jest.fn(async (url) =>
    fakeResponse(String(url).includes("org-empty"), undefined, {
      permissions: [],
      count: 0,
    })
  ) as jest.Mock;
  const { rerender } = render(
    <OrganizationSummaryCounts
      organizationId="org-empty"
      activeMembers={0}
      membersLoading={false}
    />
  );
  await screen.findByLabelText("Agents: 0");
  rerender(
    <OrganizationSummaryCounts
      organizationId="org-failed"
      activeMembers={3}
      membersLoading={false}
    />
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Agents: Unavailable")).toBeInTheDocument()
  );
  expect(screen.queryByLabelText("Agents: 0")).not.toBeInTheDocument();
});
