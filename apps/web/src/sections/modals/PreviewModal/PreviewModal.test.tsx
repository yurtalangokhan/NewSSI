import { screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import PreviewModal from "@/sections/modals/PreviewModal/PreviewModal";
import { usePreviewFile } from "@/sections/modals/PreviewModal/usePreviewFile";
import type {
  PreviewContext,
  PreviewVariant,
} from "@/sections/modals/PreviewModal/interfaces";

jest.mock("@/sections/modals/PreviewModal/usePreviewFile");

const ctx: PreviewContext = {
  fileContent: "# Başlık",
  fileBlob: null,
  fileUrl: "blob:taslak",
  fileName: "taslak.md",
  language: "markdown",
  lineCount: 1,
  fileSize: "12 B",
  zoom: 100,
  onZoomIn: jest.fn(),
  onZoomOut: jest.fn(),
  t: ((key: string) => key) as never,
};

const variant: PreviewVariant = {
  matches: () => true,
  width: "lg",
  height: "full",
  needsTextContent: true,
  headerDescription: () => "",
  renderContent: () => <p>gövde</p>,
  renderFooterLeft: () => null,
  renderFooterRight: () => null,
};

beforeEach(() => {
  jest.clearAllMocks();
  jest
    .mocked(usePreviewFile)
    .mockReturnValue({ variant, ctx, isLoading: false, loadError: null });
});

it("keeps the viewer on one surface instead of repainting the body gray", () => {
  renderWithI18n(
    <PreviewModal
      presentingDocument={{
        document_id: "d",
        semantic_identifier: "taslak.md",
      }}
      onClose={jest.fn()}
    />
  );

  const dialog = screen.getByRole("dialog");
  expect(dialog).toHaveClass("bg-background-tint-00");
  // `Modal.Body` defaults to `twoTone`, which repaints the scroll area with
  // tint-01 (#19191e in dark mode) and leaves a black/gray seam under the
  // header. The document viewer must stay on the card's surface.
  expect(dialog.querySelector(".bg-background-tint-01")).toBeNull();
});

it("shows the document skeleton while the file loads", () => {
  jest.mocked(usePreviewFile).mockReturnValue({
    variant,
    ctx,
    isLoading: true,
    loadError: null,
  });
  renderWithI18n(
    <PreviewModal
      presentingDocument={{
        document_id: "d",
        semantic_identifier: "taslak.md",
      }}
      onClose={jest.fn()}
    />
  );

  const dialog = screen.getByRole("dialog");
  expect(screen.getByTestId("document-preview-skeleton")).toBeInTheDocument();
  // The placeholder stays on the one viewer surface too.
  expect(dialog.querySelector(".bg-background-tint-01")).toBeNull();
});
