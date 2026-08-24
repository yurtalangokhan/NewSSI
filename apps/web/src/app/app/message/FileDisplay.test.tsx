import { render, screen } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";
import FileDisplay from "@/app/app/message/FileDisplay";
import { ChatFileType, FileDescriptor } from "@/app/app/interfaces";
import { MinimalOnyxDocument } from "@/lib/search/interfaces";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) =>
      ({
        "attachment.expandDocumentAriaLabel": "Expand document",
      })[key] ??
      fallback ??
      key,
  }),
  initReactI18next: { type: "3rdParty", init: jest.fn() },
}));

const textViewModalSpy = jest.fn();
jest.mock("@/sections/modals/TextViewModal", () => ({
  __esModule: true,
  default: (props: {
    presentingDocument: MinimalOnyxDocument;
    onClose: () => void;
  }) => {
    textViewModalSpy(props);
    return <div data-testid="text-view-modal">preview open</div>;
  },
}));

function makeFile(overrides: Partial<FileDescriptor> = {}): FileDescriptor {
  return {
    id: "file-1",
    type: ChatFileType.DOCUMENT,
    name: "rapor.pdf",
    ...overrides,
  };
}

describe("FileDisplay", () => {
  beforeEach(() => {
    textViewModalSpy.mockClear();
  });

  test("opening a just-sent file (inline base64 still present) previews from local data, skipping the backend fetch that could race with persistence", async () => {
    const user = userEvent.setup();
    render(
      <FileDisplay
        files={[
          makeFile({
            data: "JVBERi0xLjQK",
            mime_type: "application/pdf",
          }),
        ]}
      />
    );

    await user.click(screen.getByRole("button", { name: /expand document/i }));

    expect(textViewModalSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        presentingDocument: expect.objectContaining({
          document_id: "file-1",
          preview_url: "data:application/pdf;base64,JVBERi0xLjQK",
          preview_mime_type: "application/pdf",
        }),
      })
    );
  });

  test("opening a historical file (no inline data available) falls back to the backend fetch path", async () => {
    const user = userEvent.setup();
    render(<FileDisplay files={[makeFile()]} />);

    await user.click(screen.getByRole("button", { name: /expand document/i }));

    expect(textViewModalSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        presentingDocument: expect.objectContaining({
          document_id: "file-1",
          preview_url: undefined,
        }),
      })
    );
  });
});
