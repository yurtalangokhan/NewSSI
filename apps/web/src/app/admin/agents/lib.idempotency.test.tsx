import { uploadFile } from "@/app/admin/agents/lib";
import { authenticatedFetch } from "@/lib/fetcher";

jest.mock("@/lib/fetcher", () => ({
  authenticatedFetch: jest.fn(),
}));

describe("agent admin idempotency", () => {
  beforeEach(() => {
    jest.mocked(authenticatedFetch).mockResolvedValue(
      new Response(JSON.stringify({ file_id: "file-1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("uses authenticatedFetch for persona image upload idempotency", async () => {
    const file = new File(["avatar"], "avatar.png", { type: "image/png" });

    await uploadFile(file);

    expect(authenticatedFetch).toHaveBeenCalledWith(
      "/api/admin/persona/upload-image",
      expect.objectContaining({
        method: "POST",
        body: expect.any(FormData),
        credentials: "include",
      })
    );
  });
});
