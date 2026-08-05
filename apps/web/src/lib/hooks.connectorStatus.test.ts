import useSWR from "swr";

import { useConnectorStatus } from "@/lib/hooks";

jest.mock("swr", () => ({
  __esModule: true,
  default: jest.fn(() => ({ data: [], error: undefined, isLoading: false })),
  useSWRConfig: jest.fn(() => ({ mutate: jest.fn() })),
}));

describe("useConnectorStatus", () => {
  it("requests the available connector-status endpoint", () => {
    useConnectorStatus();

    expect(useSWR).toHaveBeenCalledWith(
      "/api/manage/connector-status",
      expect.any(Function),
      { refreshInterval: 30000 }
    );
  });
});
