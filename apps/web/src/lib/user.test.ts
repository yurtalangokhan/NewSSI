/**
 * @jest-environment jsdom
 */

import { getCurrentUser } from "@/lib/user";

function response(status: number) {
  return new Response(status === 204 ? null : "{}", {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function fetchMock() {
  return global.fetch as jest.MockedFunction<typeof fetch>;
}

describe("getCurrentUser", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
    window.history.replaceState({}, "", "/app");
    window.sessionStorage.clear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("returns null on unauthorized responses without starting auth redirects", async () => {
    fetchMock().mockResolvedValueOnce(response(401));

    await expect(getCurrentUser()).resolves.toBeNull();

    expect(fetchMock()).toHaveBeenCalledTimes(1);
    expect(fetchMock()).toHaveBeenCalledWith("/api/me", {
      credentials: "include",
    });
  });
});
