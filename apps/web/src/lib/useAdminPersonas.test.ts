import useSWR from "swr";

import { useAdminPersonas } from "@/hooks/useAdminPersonas";

jest.mock("swr", () => ({
  __esModule: true,
  default: jest.fn(() => ({
    data: [],
    error: undefined,
    isLoading: false,
    mutate: jest.fn(),
  })),
}));

describe("useAdminPersonas", () => {
  it("requests personas from the current non-paginated endpoint", () => {
    useAdminPersonas();

    expect(useSWR).toHaveBeenCalledWith(
      "/api/persona?include_deleted=false&get_editable=false",
      expect.any(Function)
    );
  });
});
