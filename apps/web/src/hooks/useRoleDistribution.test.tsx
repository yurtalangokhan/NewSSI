import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import { fetchRoleDistribution } from "@/lib/api/domains/access/api";
import useRoleDistribution from "./useRoleDistribution";

jest.mock("@/lib/api/domains/access/api", () => ({
  fetchRoleDistribution: jest.fn(),
}));

const fetcher = jest.mocked(fetchRoleDistribution);
const ready = {
  status: "ready",
  distribution: [{ role: "enduser", count: 7 }],
  computed_at: "2026-09-24T08:00:00+00:00",
};

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        provider: () => new Map(),
        dedupingInterval: 0,
        shouldRetryOnError: false,
      }}
    >
      {children}
    </SWRConfig>
  );
}

beforeEach(() => {
  fetcher.mockReset();
});

test("exposes a computed distribution as ready", async () => {
  fetcher.mockResolvedValue(ready);

  const { result } = renderHook(() => useRoleDistribution(), { wrapper });

  expect(result.current.state).toBe("loading");
  await waitFor(() => expect(result.current.state).toBe("ready"));
  expect(result.current.distribution).toEqual(ready.distribution);
  expect(fetcher).toHaveBeenCalledTimes(1);
});

test("reports calculating while the snapshot is pending and polls until ready", async () => {
  fetcher
    .mockResolvedValueOnce({
      status: "pending",
      distribution: [],
      computed_at: null,
    })
    .mockResolvedValue(ready);

  const states: string[] = [];
  const { result } = renderHook(
    () => {
      const current = useRoleDistribution({ pollIntervalMs: 10 });
      states.push(current.state);
      return current;
    },
    { wrapper }
  );

  await waitFor(() => expect(result.current.state).toBe("ready"));
  const seen = states.filter((state, i) => state !== states[i - 1]);
  expect(seen).toEqual(["loading", "calculating", "ready"]);
  expect(result.current.distribution).toEqual(ready.distribution);
});

test("stops polling once the distribution is ready", async () => {
  fetcher.mockResolvedValue(ready);

  const { result } = renderHook(
    () => useRoleDistribution({ pollIntervalMs: 10 }),
    { wrapper }
  );
  await waitFor(() => expect(result.current.state).toBe("ready"));
  const calls = fetcher.mock.calls.length;

  await new Promise((resolve) => setTimeout(resolve, 60));
  expect(fetcher.mock.calls.length).toBe(calls);
});

test("reports unavailable when the backend could not compute it", async () => {
  fetcher.mockResolvedValue({
    status: "unavailable",
    distribution: [],
    computed_at: null,
  });

  const { result } = renderHook(() => useRoleDistribution(), { wrapper });

  await waitFor(() => expect(result.current.state).toBe("unavailable"));
});

test("reports unavailable instead of loading forever when the request fails", async () => {
  fetcher.mockRejectedValue(new Error("504 Gateway Time-out"));

  const { result } = renderHook(() => useRoleDistribution(), { wrapper });

  await waitFor(() => expect(result.current.state).toBe("unavailable"));
  expect(result.current.distribution).toEqual([]);
});
