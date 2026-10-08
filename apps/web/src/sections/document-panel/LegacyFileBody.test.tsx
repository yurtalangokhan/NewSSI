import { screen } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { LegacyFileBody } from "@/sections/document-panel/LegacyFileBody";

jest.mock("@/sections/modals/PreviewModal/usePreviewFile", () => ({
  usePreviewFile: () => ({
    isLoading: false,
    loadError: null,
    ctx: { fileName: "eski.pdf" },
    variant: {
      renderContent: () => <div data-testid="variant-body">pdf body</div>,
      renderFooterRight: () => <button type="button">download</button>,
    },
  }),
}));

it("renders the preview variant read-only with the legacy notice", () => {
  renderWithI18n(
    <LegacyFileBody
      file={{ fileId: "f", filename: "eski.pdf", mimeType: "application/pdf" }}
    />,
    "tr"
  );

  expect(
    screen.getByText(
      "Bu dosya taslak geçmişi olmadan oluşturuldu; salt okunur açılıyor."
    )
  ).toBeInTheDocument();
  expect(screen.getByTestId("variant-body")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "download" })).toBeInTheDocument();
});
