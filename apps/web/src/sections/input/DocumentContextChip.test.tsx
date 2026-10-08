import { act, fireEvent, screen, within } from "@testing-library/react";
import { renderWithI18n } from "@tests/setup/renderWithI18n";
import { DocumentContextChip } from "@/sections/input/DocumentContextChip";
import { useAuthoredDocument } from "@/lib/api/domains/documents/hooks";
import {
  initialDocumentPanelState,
  useDocumentPanelStore,
} from "@/app/app/stores/useDocumentPanelStore";

jest.mock("@/lib/api/domains/documents/hooks", () => ({
  useAuthoredDocument: jest.fn(),
}));

beforeEach(() => {
  useDocumentPanelStore.setState(initialDocumentPanelState);
  jest.mocked(useAuthoredDocument).mockReturnValue({
    data: {
      title: null,
      filename: "Tedarikci_Onboarding_Sureci.docx",
      head_revision_no: 3,
    },
  } as never);
});

it("is hidden while no document is open", () => {
  renderWithI18n(<DocumentContextChip />, "tr");
  expect(screen.queryByTestId("document-context-chip")).not.toBeInTheDocument();
});

it("shows the viewed draft and can be removed", () => {
  act(() => {
    useDocumentPanelStore.getState().openDocument("d");
    useDocumentPanelStore.getState().syncHead("d", 3);
  });
  renderWithI18n(<DocumentContextChip />, "tr");

  const chip = screen.getByTestId("document-context-chip");
  expect(chip).toHaveTextContent(
    "Bağlam: Tedarikci_Onboarding_Sureci · Taslak 3"
  );
  fireEvent.click(within(chip).getByRole("button"));
  expect(useDocumentPanelStore.getState().contextEnabled).toBe(false);
  expect(screen.queryByTestId("document-context-chip")).not.toBeInTheDocument();
});
