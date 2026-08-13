import useSWR from "swr";

import { usePersonaOptions } from "@/hooks/usePersonaOptions";

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
  it("requests the lightweight persona assignment endpoint", () => {
    usePersonaOptions();

    expect(useSWR).toHaveBeenCalledWith(
      "/api/persona/options",
      expect.any(Function),
      expect.objectContaining({ revalidateOnFocus: false })
    );
  });
});
