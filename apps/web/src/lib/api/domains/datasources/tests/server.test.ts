import { backendRequest } from "@/lib/api/http/server";
import { fetchConnectorsSS } from "../server";

jest.mock("@/lib/api/http/server", () => ({ backendRequest: jest.fn() }));
jest.mock("@/lib/api/server-context", () => ({
  getServerRequestHeaders: jest.fn().mockResolvedValue({ cookie: "session=1" }),
}));

it("loads connectors through the datasource server operation", async () => {
  const response = new Response("[]");
  jest.mocked(backendRequest).mockResolvedValue(response);

  await expect(fetchConnectorsSS()).resolves.toBe(response);
  expect(backendRequest).toHaveBeenCalledWith(
    expect.objectContaining({
      service: "agent",
      path: "/api/v1/manage/connector",
    })
  );
});
