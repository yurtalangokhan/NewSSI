import { apiRequest } from "@/lib/api/http/browser";
import { fetchBillingLicense } from "@/lib/api/domains/billing/api";

jest.mock("@/lib/api/http/browser", () => ({
  apiRequest: jest.fn(async () => ({ ok: true, json: async () => ({}) })),
  parseJsonResponse: jest.fn(async (res: Response) => res.json()),
}));

// Every admin page reads the license through AdminSidebar. Only the local
// /api/license route answers it; any other path 403s, and apiRequest turns
// that 403 into a full-page redirect to /error/403.
it("reads the license from the local /api/license route", async () => {
  await fetchBillingLicense();

  expect(apiRequest).toHaveBeenCalledWith("/api/license");
});
