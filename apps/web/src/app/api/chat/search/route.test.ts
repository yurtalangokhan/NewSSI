import { GET } from "@/app/api/chat/search/route";

describe("GET /api/chat/search", () => {
  it("returns the chat search response contract", async () => {
    const request = new Request(
      "http://localhost/api/chat/search?query=quarterly&page=1&page_size=20"
    );

    const response = await GET(request);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      groups: [],
      has_more: false,
      next_page: null,
    });
  });
});
