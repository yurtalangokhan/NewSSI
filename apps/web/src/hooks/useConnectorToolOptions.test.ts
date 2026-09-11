import useSWR from "swr";
import { renderHook } from "@testing-library/react";

import useConnectorToolOptions from "./useConnectorToolOptions";
import { errorHandlingFetcher } from "@/lib/fetcher";

jest.mock("swr");
jest.mock("@/lib/fetcher", () => ({ errorHandlingFetcher: jest.fn() }));

it("loads configured connector tool options through the agent proxy", () => {
  (useSWR as jest.Mock).mockReturnValue({ data: [], isLoading: false });

  renderHook(() => useConnectorToolOptions());

  expect(useSWR).toHaveBeenCalledWith(
    "/api/agent/datasources/tool-options",
    errorHandlingFetcher
  );
});
