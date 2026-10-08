import { act, renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";
import type { ReactNode } from "react";
import {
  documentKeys,
  refreshAuthoredDocument,
  useAuthoredDocument,
  useRevision,
  useRevisionPair,
} from "@/lib/api/domains/documents/hooks";
import * as api from "@/lib/api/domains/documents/api";

jest.mock("@/lib/api/domains/documents/api");

function wrapper({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {children}
    </SWRConfig>
  );
}

describe("documents hooks", () => {
  beforeEach(() => jest.resetAllMocks());

  it("does not fetch without an id", () => {
    renderHook(() => useAuthoredDocument(null), { wrapper });
    expect(api.fetchAuthoredDocument).not.toHaveBeenCalled();
  });

  it("loads a document", async () => {
    jest
      .mocked(api.fetchAuthoredDocument)
      .mockResolvedValue({ document_id: "d", head_revision_no: 2 } as never);
    const { result } = renderHook(() => useAuthoredDocument("d"), { wrapper });

    await waitFor(() => expect(result.current.data?.head_revision_no).toBe(2));
    expect(api.fetchAuthoredDocument).toHaveBeenCalledWith("d");
  });

  it("loads both sides of a pair and skips a missing side", async () => {
    jest
      .mocked(api.fetchRevision)
      .mockImplementation(async (_d, no) => ({ revision_no: no }) as never);
    const { result } = renderHook(() => useRevisionPair("d", null, 3), {
      wrapper,
    });

    await waitFor(() => expect(result.current.right.data?.revision_no).toBe(3));
    expect(result.current.left.data).toBeUndefined();
    expect(api.fetchRevision).toHaveBeenCalledTimes(1);
  });

  it("exposes a failed side and retries both sides", async () => {
    jest
      .mocked(api.fetchRevision)
      .mockRejectedValueOnce(new Error("boom"))
      .mockImplementation(async (_d, no) => ({ revision_no: no }) as never);
    const { result } = renderHook(() => useRevisionPair("d", 1, 2), {
      wrapper,
    });
    await waitFor(() => expect(result.current.error).toBeDefined());

    await act(async () => {
      await result.current.retry();
    });

    await waitFor(() => expect(result.current.error).toBeUndefined());
    expect(result.current.left.data?.revision_no).toBe(1);
    expect(result.current.right.data?.revision_no).toBe(2);
  });

  it("keys revisions by document and number", () => {
    expect(documentKeys.revision("d", 4)).toBe("/api/documents/d/revisions/4");
    expect(documentKeys.document("d")).toBe("/api/documents/d");
  });

  it("refreshAuthoredDocument returns a promise", async () => {
    await expect(refreshAuthoredDocument("d")).resolves.toBeUndefined();
  });

  it("useRevision fetches once per key", async () => {
    jest
      .mocked(api.fetchRevision)
      .mockResolvedValue({ revision_no: 1 } as never);
    const { result, rerender } = renderHook(() => useRevision("d", 1), {
      wrapper,
    });
    await waitFor(() => expect(result.current.data?.revision_no).toBe(1));
    rerender();
    expect(api.fetchRevision).toHaveBeenCalledTimes(1);
  });
});
