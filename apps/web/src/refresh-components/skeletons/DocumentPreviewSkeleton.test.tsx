import { render, screen } from "@testing-library/react";
import DocumentPreviewSkeleton from "@/refresh-components/skeletons/DocumentPreviewSkeleton";

it("announces a loading document and draws the page shape", () => {
  const { container } = render(<DocumentPreviewSkeleton />);

  const status = screen.getByTestId("document-preview-skeleton");
  expect(status).toHaveAttribute("role", "status");
  expect(status).toHaveAttribute("aria-label", "Loading document...");
  // Title, meta, two paragraph groups (3 lines each) and the wide block.
  expect(container.querySelectorAll(".animate-pulse")).toHaveLength(9);
});

it("drops the paper frame and the block when asked", () => {
  const { container } = render(
    <DocumentPreviewSkeleton
      paper={false}
      showBlock={false}
      paragraphCount={1}
    />
  );

  expect(screen.getByTestId("document-preview-skeleton")).not.toHaveClass(
    "bg-background-tint-00"
  );
  // Title, meta and one paragraph on each side of where the block would be.
  expect(container.querySelectorAll(".animate-pulse")).toHaveLength(4);
});
