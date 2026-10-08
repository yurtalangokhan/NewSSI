import { apiRequest } from "@/lib/api/http/browser";
import { envelopeResponse } from "@tests/setup/responseModel";
import {
  searchOrganizationTree,
  fetchOrganizationAncestors,
  fetchOrganizationChildren,
} from "@/lib/api/domains/access/api";

jest.mock("@/lib/api/http/browser", () => ({ apiRequest: jest.fn() }));

beforeEach(() => {
  jest.mocked(apiRequest).mockReset();
  jest.mocked(apiRequest).mockImplementation(async () => envelopeResponse([]));
});

it("preserves non-redirecting organization probes from dev", async () => {
  const signal = new AbortController().signal;
  await searchOrganizationTree("a%20b", signal, false);
  await fetchOrganizationAncestors("org-1", false);
  await fetchOrganizationChildren("org-1", false);
  expect(apiRequest).toHaveBeenNthCalledWith(
    1,
    "/api/user-service/organizations/search?q=a%20b&max_results=100",
    { signal, redirectOnAuthError: false }
  );
  expect(apiRequest).toHaveBeenNthCalledWith(
    2,
    "/api/user-service/organizations/org-1/ancestors",
    { redirectOnAuthError: false }
  );
  expect(apiRequest).toHaveBeenNthCalledWith(
    3,
    "/api/user-service/organizations/org-1/children",
    { redirectOnAuthError: false }
  );
});
