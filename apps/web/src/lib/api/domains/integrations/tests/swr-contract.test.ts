import {
  fetchOAuthStatus,
  fetchSlackChannelConfigs,
  fetchSlackBots,
  fetchSlackBot,
  fetchSlackChannelConfigsByBot,
  fetchDiscordGuilds,
  fetchDiscordGuild,
  fetchDiscordChannels,
} from "../api";
import { apiRequest } from "@/lib/api/http/browser";
import { FetchError } from "@/lib/api/http/errors";
import i18n from "@/i18n/config";

jest.mock("@/lib/api/http/browser", () => ({
  ...jest.requireActual("@/lib/api/http/browser"),
  apiRequest: jest.fn(),
}));
const request = jest.mocked(apiRequest);
const operations: Array<[string, () => Promise<unknown>]> = [
  ["fetchOAuthStatus", () => fetchOAuthStatus()],
  ["fetchSlackChannelConfigs", () => fetchSlackChannelConfigs()],
  ["fetchSlackBots", () => fetchSlackBots()],
  ["fetchSlackBot", () => fetchSlackBot(1)],
  ["fetchSlackChannelConfigsByBot", () => fetchSlackChannelConfigsByBot(1)],
  ["fetchDiscordGuilds", () => fetchDiscordGuilds()],
  ["fetchDiscordGuild", () => fetchDiscordGuild(1)],
  ["fetchDiscordChannels", () => fetchDiscordChannels(1)],
];
describe.each(operations)("%s legacy SWR contract", (_name, load) => {
  beforeEach(() => request.mockReset());
  it("rejects HTTP errors instead of caching them as successful data", async () => {
    request.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Access denied" }), { status: 403 })
    );
    await expect(load()).rejects.toBeInstanceOf(FetchError);
  });
  it("preserves invalid successful JSON fallback and language header", async () => {
    request.mockResolvedValue(new Response("not-json", { status: 200 }));
    await expect(load()).resolves.toEqual({});
    expect(request).toHaveBeenCalledWith(expect.any(String), {
      headers: { "X-Language": i18n.language },
    });
  });
  it("preserves successful response data and network failures", async () => {
    request.mockResolvedValue(new Response(JSON.stringify({ items: ["one"] })));
    await expect(load()).resolves.toEqual({ items: ["one"] });
    const failure = new Error("network unavailable");
    request.mockRejectedValue(failure);
    await expect(load()).rejects.toBe(failure);
  });
});
