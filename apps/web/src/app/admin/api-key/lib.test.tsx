import { createApiKey } from "@/app/admin/api-key/lib";

describe("admin API key client", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("creates API keys without sending legacy role payload", async () => {
    const fetchMock = jest
      .spyOn(global, "fetch")
      // /api/admin/api-key create
      .mockResolvedValue({ ok: true } as Response);

    await createApiKey({ name: "service-client" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/admin/api-key",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "service-client" }),
      })
    );
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.has("Idempotency-Key")).toBe(true);
  });
});
