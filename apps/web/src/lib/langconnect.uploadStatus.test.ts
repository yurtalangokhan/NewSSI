import useSWR from "swr";

import { useUploadStatus } from "@/lib/langconnect";

jest.mock("swr", () => ({
  __esModule: true,
  default: jest.fn(() => ({
    data: undefined,
    error: undefined,
    isLoading: false,
    mutate: jest.fn(),
  })),
}));

describe("useUploadStatus", () => {
  afterEach(() => {
    (useSWR as jest.Mock).mockClear();
  });

  it("polls the upload-jobs status endpoint when active", () => {
    useUploadStatus("col-1", true);

    expect(useSWR).toHaveBeenCalledWith(
      "/api/rag/collections/col-1/documents/upload-jobs/status",
      expect.any(Function),
      { refreshInterval: 2_000 }
    );
  });

  it("does not poll when inactive", () => {
    useUploadStatus("col-1", false);

    expect(useSWR).toHaveBeenCalledWith(null, expect.any(Function), {
      refreshInterval: 2_000,
    });
  });

  it("does not poll when there is no collection selected", () => {
    useUploadStatus(null, true);

    expect(useSWR).toHaveBeenCalledWith(null, expect.any(Function), {
      refreshInterval: 2_000,
    });
  });
});
