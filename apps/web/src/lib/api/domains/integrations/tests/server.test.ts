import { backendRequest } from "@/lib/api/http/server";
import { fetchSlackChannelsSS } from "../server";

jest.mock("@/lib/api/http/server", () => ({ backendRequest: jest.fn() }));
jest.mock("@/lib/api/server-context", () => ({
  getServerRequestHeaders: jest.fn().mockResolvedValue({ cookie: "session=1" }),
}));

it("loads Slack channels through the integrations server operation", async () => {
  jest.mocked(backendRequest).mockResolvedValue(new Response("[]"));

  await fetchSlackChannelsSS();
  expect(backendRequest).toHaveBeenCalledWith(
    expect.objectContaining({
      service: "agent",
      path: "/api/v1/manage/admin/slack-app/channel",
    })
  );
});
