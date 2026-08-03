import { transformApiResponse } from "@/sections/sidebar/useChatSearchOptimistic";

describe("transformApiResponse", () => {
  it("returns no chats when groups is missing", () => {
    expect(transformApiResponse({})).toEqual([]);
  });
});
