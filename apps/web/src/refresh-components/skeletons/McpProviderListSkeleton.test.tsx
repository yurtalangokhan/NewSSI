import { render, screen } from "@testing-library/react";
import McpProviderListSkeleton from "@/refresh-components/skeletons/McpProviderListSkeleton";

it("announces a loading provider list and draws one row per provider", () => {
  render(<McpProviderListSkeleton />);

  const status = screen.getByTestId("mcp-provider-list-skeleton");
  expect(status).toHaveAttribute("role", "status");
  expect(status).toHaveAttribute("aria-label", "Loading providers...");
  expect(screen.getAllByTestId("mcp-provider-skeleton-row")).toHaveLength(3);
});

it("draws the requested number of rows", () => {
  render(<McpProviderListSkeleton rowCount={5} />);

  expect(screen.getAllByTestId("mcp-provider-skeleton-row")).toHaveLength(5);
});
