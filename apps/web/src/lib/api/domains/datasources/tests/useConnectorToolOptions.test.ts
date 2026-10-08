/** @jest-environment jsdom */
import useSWR from "swr";
import { renderHook } from "@testing-library/react";
import { useConnectorToolOptions } from "@/lib/api/domains/datasources/hooks";
import { fetchConnectorToolOptions } from "@/lib/api/domains/datasources/api";

jest.mock("swr");
jest.mock("@/lib/api/domains/datasources/api", () => ({
  fetchConnectorToolOptions: jest.fn(),
}));

it("loads configured connector tool options through the domain API", () => {
  (useSWR as jest.Mock).mockReturnValue({ data: [], isLoading: false });
  renderHook(() => useConnectorToolOptions());
  expect(useSWR).toHaveBeenCalledWith(
    "/api/agent/datasources/tool-options",
    fetchConnectorToolOptions
  );
});
