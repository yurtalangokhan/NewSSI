import { backendRequest } from "@/lib/api/http/server";
import {
  fetchCustomAnalyticsScriptSS,
  fetchEnterpriseSettingsSS,
  fetchWebVersionSS,
} from "../server";

jest.mock("@/lib/api/http/server", () => ({ backendRequest: jest.fn() }));
jest.mock("@/lib/api/server-context", () => ({
  getServerRequestHeaders: jest.fn().mockResolvedValue({ cookie: "session=1" }),
}));

it("owns the system server request targets", async () => {
  jest.mocked(backendRequest).mockResolvedValue(new Response("{}"));

  await fetchEnterpriseSettingsSS();
  await fetchCustomAnalyticsScriptSS();
  await fetchWebVersionSS();

  expect(
    jest.mocked(backendRequest).mock.calls.map(([call]) => call.path)
  ).toEqual([
    "/api/v1/enterprise-settings",
    "/api/v1/enterprise-settings/custom-analytics-script",
    "/api/v1/version",
  ]);
});
