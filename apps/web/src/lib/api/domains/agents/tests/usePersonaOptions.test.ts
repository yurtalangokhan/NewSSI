import useSWR from "swr";

import { usePersonaOptions } from "@/lib/api/domains/agents/hooks";

jest.mock("swr", () => ({
  __esModule: true,
  default: jest.fn(() => ({
    data: [],
    error: undefined,
    isLoading: false,
    mutate: jest.fn(),
  })),
}));

describe("usePersonaOptions", () => {
  it("returns one option per ID while preserving first entries and order", () => {
    const firstAgent = { id: 1, name: "Research", description: "First entry" };
    const otherAgent = {
      id: 2,
      name: "Research",
      description: "Distinct agent",
    };
    const refresh = jest.fn();
    jest.mocked(useSWR).mockReturnValueOnce({
      data: [
        firstAgent,
        otherAgent,
        { id: 1, name: "Repeated research", description: "Duplicate entry" },
      ],
      error: undefined,
      isLoading: false,
      isValidating: false,
      mutate: refresh,
    });

    expect(usePersonaOptions()).toEqual({
      personas: [firstAgent, otherAgent],
      error: undefined,
      isLoading: false,
      refresh,
    });
  });

  it("requests the lightweight persona assignment endpoint", () => {
    usePersonaOptions();

    expect(useSWR).toHaveBeenCalledWith(
      "/api/persona/options",
      expect.any(Function),
      expect.objectContaining({ revalidateOnFocus: false })
    );
  });
});
