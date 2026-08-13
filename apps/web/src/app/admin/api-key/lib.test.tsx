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

    expect(fetchMock).toHaveBeenCalledWith("/api/admin/api-key", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name: "service-client" }),
    });
  });
});
