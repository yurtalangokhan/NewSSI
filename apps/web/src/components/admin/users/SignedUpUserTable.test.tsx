/**
 * @jest-environment jsdom
 */

import { render, screen } from "@tests/setup/test-utils";
import SignedUpUserTable from "@/components/admin/users/SignedUpUserTable";
import usePaginatedFetch from "@/hooks/usePaginatedFetch";

jest.mock("@/hooks/usePaginatedFetch");
jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({ user: { id: "current-user" } }),
}));

const mockedUsePaginatedFetch = usePaginatedFetch as jest.MockedFunction<
  typeof usePaginatedFetch
>;

function paginatedState(error: Error | null = null) {
  return {
    currentPageData: [],
    isLoading: false,
    error,
    currentPage: 1,
    totalPages: 1,
    goToPage: jest.fn(),
    refresh: jest.fn(),
    updateItem: jest.fn(),
    totalItems: 0,
  };
}

describe("SignedUpUserTable", () => {
  beforeEach(() => {
    mockedUsePaginatedFetch.mockReturnValue(paginatedState());
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it("keeps hook order stable when the users request moves into an error state", () => {
    const { rerender } = render(<SignedUpUserTable q="" />);

    mockedUsePaginatedFetch.mockReturnValue(
      paginatedState(new Error("Failed to load users"))
    );

    expect(() => rerender(<SignedUpUserTable q="" />)).not.toThrow();
    expect(screen.getByText("Failed to load users")).toBeInTheDocument();
  });
});
