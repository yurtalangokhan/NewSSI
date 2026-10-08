import { backendRequest } from "@/lib/api/http/server";
import { fetchAgentsSS } from "../server";
import { envelopeResponse } from "@tests/setup/responseModel";

jest.mock("@/lib/api/http/server", () => ({ backendRequest: jest.fn() }));
jest.mock("@/lib/api/server-context", () => ({
  getServerRequestHeaders: jest.fn().mockResolvedValue({ cookie: "session=1" }),
}));

it("loads personas through the agents server operation", async () => {
  jest.mocked(backendRequest).mockResolvedValue(envelopeResponse([{ id: 1 }]));

  await expect(fetchAgentsSS()).resolves.toEqual([[{ id: 1 }], null]);
  expect(backendRequest).toHaveBeenCalledWith(
    expect.objectContaining({ service: "agent", path: "/api/v1/persona" })
  );
});
