/**
 * @jest-environment jsdom
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import useSWR, { SWRConfig } from "swr";

import {
  useOrganizationLayout,
  type OrganizationLayoutResponse,
} from "@/components/organization/useOrganizationLayout";

const remoteLayout: OrganizationLayoutResponse = {
  positions: [
    { organization_id: "root", x: 10, y: 20 },
    { organization_id: "read-only", x: 30, y: 40 },
  ],
  writable_organization_ids: ["root"],
};
const layoutKey = "/api/user-service/organizations/layout";

function swrWrapper({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map() }}>{children}</SWRConfig>
  );
}

function useCachedLayoutConsumer() {
  const { data } = useSWR<OrganizationLayoutResponse>(layoutKey, null, {
    revalidateOnMount: false,
  });
  return data;
}

describe("useOrganizationLayout", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it("exposes backend load detail and ends loading after a rejected layout request", async () => {
    // Serves the organization layout GET request.
    jest.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Layout access is denied" }), {
        status: 403,
      })
    );
    const { result } = renderHook(() => useOrganizationLayout(), {
      wrapper: swrWrapper,
    });

    await waitFor(() => {
      expect(result.current.error?.message).toBe("Layout access is denied");
      expect(result.current.isLoading).toBe(false);
    });
  });

  it("does not retry a failed layout load on SWR's five-second timer", async () => {
    const fetchSpy = jest
      .spyOn(global, "fetch")
      // Serves the organization layout GET with a persistent backend failure.
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: "Layout table is unavailable" }), {
          status: 500,
        })
      );
    const { result } = renderHook(() => useOrganizationLayout(), {
      wrapper: swrWrapper,
    });

    await waitFor(() => expect(result.current.error).toBeDefined());
    await act(async () => {
      jest.advanceTimersByTime(6_000);
      await Promise.resolve();
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("exposes backend save messages and returns false when a layout write fails", async () => {
    // Serves the organization layout GET followed by its failing PUT request.
    jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify(remoteLayout), { status: 200 })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ message: "Layout is locked" }), {
          status: 409,
        })
      );
    const { result } = renderHook(() => useOrganizationLayout(), {
      wrapper: swrWrapper,
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => {
      result.current.setPosition("root", { x: 100, y: 200 });
    });
    let saved!: boolean;
    await act(async () => {
      saved = await result.current.flush();
    });

    expect(saved).toBe(false);
    expect(result.current.error?.message).toBe("Layout is locked");
  });

  it("debounces writable dirty positions into one bulk save", async () => {
    const saveLayout = jest.fn().mockResolvedValue({ positions: [], count: 1 });
    const { result } = renderHook(() =>
      useOrganizationLayout({
        remoteLayout,
        saveLayout,
        debounceMs: 250,
      })
    );

    act(() => {
      result.current.setPosition("root", { x: 100, y: 200 });
      result.current.setPosition("root", { x: 120, y: 240 });
      result.current.setPosition("read-only", { x: 300, y: 400 });
      jest.advanceTimersByTime(250);
    });

    await waitFor(() =>
      expect(saveLayout).toHaveBeenCalledWith([
        { organization_id: "root", x: 120, y: 240 },
      ])
    );
    await waitFor(() => expect(result.current.status).toBe("saved"));
    expect(result.current.positions.root).toEqual({ x: 120, y: 240 });
    expect(result.current.positions["read-only"]).toEqual({ x: 30, y: 40 });
  });

  it("keeps failed local positions across remote refreshes and retries them", async () => {
    const saveLayout = jest
      .fn()
      .mockRejectedValueOnce(new Error("Save failed"))
      .mockResolvedValueOnce({ positions: [], count: 1 });
    const { result, rerender } = renderHook(
      ({ layout }) =>
        useOrganizationLayout({ layout, saveLayout, debounceMs: 250 }),
      { initialProps: { layout: remoteLayout } }
    );

    act(() => {
      result.current.setPosition("root", { x: 100, y: 200 });
    });
    await act(async () => {
      await result.current.flush();
    });

    expect(result.current.status).toBe("error");
    rerender({
      layout: {
        ...remoteLayout,
        positions: [{ organization_id: "root", x: 5, y: 5 }],
      },
    });
    expect(result.current.positions.root).toEqual({ x: 100, y: 200 });

    await act(async () => {
      await result.current.retry();
    });

    expect(saveLayout).toHaveBeenLastCalledWith([
      { organization_id: "root", x: 100, y: 200 },
    ]);
    expect(result.current.status).toBe("saved");
  });

  it("discards unsaved positions and restores the latest remote layout", () => {
    const { result } = renderHook(() =>
      useOrganizationLayout({ remoteLayout, saveLayout: jest.fn() })
    );

    act(() => {
      result.current.setPosition("root", { x: 99, y: 99 });
      result.current.discard();
    });

    expect(result.current.positions.root).toEqual({ x: 10, y: 20 });
    expect(result.current.hasDirtyPositions).toBe(false);
  });

  it("keeps the complete remote baseline when a partial save response is discarded", async () => {
    const saveLayout = jest.fn().mockResolvedValue({
      positions: [{ organization_id: "root", x: 99, y: 99 }],
      count: 1,
    });
    const { result } = renderHook(() =>
      useOrganizationLayout({ remoteLayout, saveLayout })
    );

    act(() => {
      result.current.setPosition("root", { x: 99, y: 99 });
    });
    await act(async () => {
      await result.current.flush();
    });
    act(() => {
      result.current.setPosition("root", { x: 100, y: 100 });
      result.current.discard();
    });

    expect(result.current.positions.root).toEqual({ x: 99, y: 99 });
    expect(result.current.positions["read-only"]).toEqual({ x: 30, y: 40 });
  });

  it("shares merged saved layout with a remounted consumer without another GET", async () => {
    const cache = new Map();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <SWRConfig value={{ provider: () => cache }}>{children}</SWRConfig>
    );
    // Serves the organization layout GET followed by its successful PUT request.
    const fetchSpy = jest
      .spyOn(global, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify(remoteLayout), { status: 200 })
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            positions: [{ organization_id: "root", x: 99, y: 99 }],
            count: 1,
          }),
          { status: 200 }
        )
      );
    const { result, unmount } = renderHook(() => useOrganizationLayout(), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => {
      result.current.setPosition("root", { x: 99, y: 99 });
    });
    await act(async () => {
      await result.current.flush();
    });
    unmount();

    const { result: cachedResult } = renderHook(useCachedLayoutConsumer, {
      wrapper,
    });

    expect(cachedResult.current?.positions).toEqual([
      { organization_id: "read-only", x: 30, y: 40 },
      { organization_id: "root", x: 99, y: 99 },
    ]);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it("flushes a newer position that arrives while an active save is settling", async () => {
    let resolveFirstSave: (() => void) | undefined;
    const saveLayout = jest
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<{ positions: []; count: 1 }>((resolve) => {
            resolveFirstSave = () => resolve({ positions: [], count: 1 });
          })
      )
      .mockResolvedValueOnce({ positions: [], count: 1 });
    const { result } = renderHook(() =>
      useOrganizationLayout({ remoteLayout, saveLayout })
    );

    act(() => {
      result.current.setPosition("root", { x: 100, y: 200 });
    });
    let flushPromise!: Promise<boolean>;
    act(() => {
      flushPromise = result.current.flush();
    });
    act(() => {
      result.current.setPosition("root", { x: 150, y: 250 });
      resolveFirstSave?.();
    });
    await act(async () => {
      await flushPromise;
    });

    expect(saveLayout).toHaveBeenNthCalledWith(1, [
      { organization_id: "root", x: 100, y: 200 },
    ]);
    expect(saveLayout).toHaveBeenNthCalledWith(2, [
      { organization_id: "root", x: 150, y: 250 },
    ]);
  });

  it("auto-saves a debounced edit made while another save is active", async () => {
    let resolveFirstSave: (() => void) | undefined;
    const saveLayout = jest
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise<{ positions: []; count: 1 }>((resolve) => {
            resolveFirstSave = () => resolve({ positions: [], count: 1 });
          })
      )
      .mockResolvedValueOnce({ positions: [], count: 1 });
    const { result } = renderHook(() =>
      useOrganizationLayout({ remoteLayout, saveLayout, debounceMs: 250 })
    );

    act(() => {
      result.current.setPosition("root", { x: 100, y: 200 });
      jest.advanceTimersByTime(250);
      result.current.setPosition("root", { x: 150, y: 250 });
      jest.advanceTimersByTime(250);
      resolveFirstSave?.();
    });

    await waitFor(() =>
      expect(saveLayout).toHaveBeenNthCalledWith(2, [
        { organization_id: "root", x: 150, y: 250 },
      ])
    );
  });

  it("returns false from a failed flush and keeps the local position", async () => {
    const { result } = renderHook(() =>
      useOrganizationLayout({
        remoteLayout,
        saveLayout: jest.fn().mockRejectedValue(new Error("Save failed")),
      })
    );

    act(() => {
      result.current.setPosition("root", { x: 100, y: 200 });
    });
    let saved!: boolean;
    await act(async () => {
      saved = await result.current.flush();
    });

    expect(saved).toBe(false);
    expect(result.current.positions.root).toEqual({ x: 100, y: 200 });
    expect(result.current.status).toBe("error");
  });

  it("does not update state after an active request settles following unmount", async () => {
    let resolveSave: (() => void) | undefined;
    const saveLayout = jest.fn(
      () =>
        new Promise<{ positions: []; count: 1 }>((resolve) => {
          resolveSave = () => resolve({ positions: [], count: 1 });
        })
    );
    const { result, unmount } = renderHook(() =>
      useOrganizationLayout({ remoteLayout, saveLayout })
    );
    const consoleErrorSpy = jest
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    act(() => {
      result.current.setPosition("root", { x: 100, y: 200 });
      void result.current.flush();
      unmount();
      resolveSave?.();
    });

    await act(async () => {
      await Promise.resolve();
    });
    expect(saveLayout).toHaveBeenCalledTimes(1);
    expect(consoleErrorSpy.mock.calls.flat().join(" ")).not.toMatch(
      /unmounted component|state update/i
    );
  });

  it("cancels a pending debounce when unmounted", () => {
    const saveLayout = jest.fn();
    const { result, unmount } = renderHook(() =>
      useOrganizationLayout({ remoteLayout, saveLayout, debounceMs: 250 })
    );

    act(() => {
      result.current.setPosition("root", { x: 100, y: 200 });
      unmount();
      jest.advanceTimersByTime(250);
    });

    expect(saveLayout).not.toHaveBeenCalled();
  });
});
