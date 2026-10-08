import {
  deleteAgent,
  updateAgentSharedStatus,
  updateAgentFeaturedStatus,
} from "../api";
import { apiRequest } from "@/lib/api/http/browser";
import { envelope, envelopeResponse } from "@tests/setup/responseModel";

jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));

const operations: Array<[string, () => Promise<string | null>]> = [
  ["delete", () => deleteAgent(42)],
  ["share", () => updateAgentSharedStatus(42, ["user"], [3], true, true, [7])],
  ["feature", () => updateAgentFeaturedStatus(42, true)],
];

describe.each(operations)("%s mutation return contract", (_name, run) => {
  it("returns null on success, rather than a Response or throwing", async () => {
    jest.mocked(apiRequest).mockResolvedValue(envelopeResponse(null));
    await expect(run()).resolves.toBeNull();
  });
  it("returns the backend error message", async () => {
    jest.mocked(apiRequest).mockResolvedValue(
      new Response(
        JSON.stringify({
          ...envelope(null, 400),
          message: "Permission denied",
          error: { code: "permission.denied", message: "Permission denied" },
        }),
        { status: 400 }
      )
    );
    await expect(run()).resolves.toBe("Permission denied");
  });
  it("returns the legacy network error string", async () => {
    const logging = jest.spyOn(console, "error").mockImplementation(() => {});
    try {
      jest.mocked(apiRequest).mockRejectedValue(new Error("offline"));
      await expect(run()).resolves.toBe(
        "Network error. Please check your connection and try again."
      );
    } finally {
      logging.mockRestore();
    }
  });
});

it("omits enterprise-only sharing fields in non-enterprise requests", async () => {
  jest.mocked(apiRequest).mockResolvedValue(envelopeResponse(null));
  await updateAgentSharedStatus(42, ["user"], [], undefined, false, [7]);
  expect(apiRequest).toHaveBeenLastCalledWith(expect.any(String), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_ids: ["user"], label_ids: [7] }),
  });
});
