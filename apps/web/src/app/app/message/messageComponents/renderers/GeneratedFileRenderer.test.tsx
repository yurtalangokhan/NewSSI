import { render, screen } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";
import { GeneratedFileRenderer } from "@/app/app/message/messageComponents/renderers/GeneratedFileRenderer";
import { RenderType } from "@/app/app/message/messageComponents/interfaces";
import {
  GeneratedFile,
  GeneratedFilePacket,
  PacketType,
} from "@/app/app/services/streamingModels";
import { MinimalOnyxDocument } from "@/lib/search/interfaces";

// Minimal i18next stand-in: string fallbacks pass through, option objects use
// their defaultValue and get {{placeholder}} interpolation like the real thing.
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string | Record<string, unknown>) => {
      if (typeof fallback === "string") return fallback;
      const template = String(fallback?.defaultValue ?? key);
      return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
        String(fallback?.[name] ?? "")
      );
    },
  }),
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

const PLACEMENT = { turn_index: 0, tab_index: 0 };

function makePacket(
  overrides: Partial<GeneratedFile> = {}
): GeneratedFilePacket {
  return {
    placement: PLACEMENT,
    obj: {
      type: PacketType.GENERATED_FILE,
      file_id: "abc123",
      filename: "rapor.pdf",
      mime_type: "application/pdf",
      size_bytes: 24576,
      download_url: "/api/chat/file/abc123?download=1",
      ...overrides,
    } as GeneratedFile,
  };
}

function startPacket(
  overrides: Record<string, unknown> = {}
): GeneratedFilePacket {
  return {
    placement: PLACEMENT,
    obj: {
      type: PacketType.DOCUMENT_GENERATION_START,
      tool_name: "create_document",
      filename: null,
      format: null,
      phase: "writing",
      ...overrides,
    },
  } as GeneratedFilePacket;
}

function progressPacket(
  overrides: Record<string, unknown> = {}
): GeneratedFilePacket {
  return {
    placement: PLACEMENT,
    obj: {
      type: PacketType.DOCUMENT_GENERATION_PROGRESS,
      tool_name: "create_document",
      filename: "rapor",
      format: "pdf",
      phase: "writing",
      chars: 1200,
      ...overrides,
    },
  } as GeneratedFilePacket;
}

function endPacket(
  overrides: Record<string, unknown> = {}
): GeneratedFilePacket {
  return {
    placement: PLACEMENT,
    obj: {
      type: PacketType.DOCUMENT_GENERATION_END,
      tool_name: "create_document",
      filename: "rapor.pdf",
      format: "pdf",
      status: "success",
      error: null,
      ...overrides,
    },
  } as GeneratedFilePacket;
}

function renderCard(
  packets: GeneratedFilePacket[],
  onComplete = jest.fn(),
  stopPacketSeen = true
) {
  return render(
    <GeneratedFileRenderer
      packets={packets}
      state={{}}
      onComplete={onComplete}
      renderType={RenderType.FULL}
      animate={false}
      stopPacketSeen={stopPacketSeen}
    >
      {(results) => (
        <>
          {results.map((r, i) => (
            <div key={i}>{r.content}</div>
          ))}
        </>
      )}
    </GeneratedFileRenderer>
  );
}

describe("GeneratedFileRenderer", () => {
  beforeEach(() => {
    textViewModalSpy.mockClear();
  });

  test("renders filename and human-readable size", () => {
    renderCard([makePacket()]);

    expect(screen.getByText("rapor.pdf")).toBeInTheDocument();
    expect(screen.getByText("24 KB")).toBeInTheDocument();
  });

  test("does not render a raw download link — opening is via the file-preview modal", () => {
    renderCard([makePacket()]);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  test("opens the shared file-preview modal (same as uploaded files) when clicked, without downloading", async () => {
    const user = userEvent.setup();
    renderCard([makePacket()]);

    expect(screen.queryByTestId("text-view-modal")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button"));

    expect(screen.getByTestId("text-view-modal")).toBeInTheDocument();
    expect(textViewModalSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        presentingDocument: {
          document_id: "abc123",
          semantic_identifier: "rapor.pdf",
        },
      })
    );
  });

  test("finds the file packet even when a trailing SECTION_END packet is appended", () => {
    const sectionEndPacket = {
      placement: PLACEMENT,
      obj: { type: PacketType.SECTION_END },
    } as unknown as GeneratedFilePacket;

    renderCard([makePacket(), sectionEndPacket]);

    expect(screen.getByText("rapor.pdf")).toBeInTheDocument();
    expect(screen.queryByText("Unknown")).not.toBeInTheDocument();
  });

  test("calls onComplete immediately since the file is already fully known", () => {
    const onComplete = jest.fn();
    renderCard([makePacket()], onComplete);

    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  describe("while the document is still being generated", () => {
    test("shows the skeleton instead of an empty message area", () => {
      renderCard([startPacket()], jest.fn(), false);

      expect(
        screen.getByTestId("document-generation-skeleton")
      ).toBeInTheDocument();
      expect(screen.getByText("Writing document...")).toBeInTheDocument();
    });

    test("surfaces the filename and character count once they stream in", () => {
      renderCard([startPacket(), progressPacket()], jest.fn(), false);

      expect(screen.getByText("rapor.pdf")).toBeInTheDocument();
      expect(
        screen.getByText("Writing document... (1,200 characters)")
      ).toBeInTheDocument();
    });

    test("switches the label when the model finishes writing and rendering starts", () => {
      renderCard(
        [startPacket(), progressPacket({ phase: "rendering", chars: 0 })],
        jest.fn(),
        false
      );

      expect(screen.getByText("Preparing file...")).toBeInTheDocument();
    });

    test("does not report completion until the generation settles", () => {
      const onComplete = jest.fn();
      renderCard([startPacket(), progressPacket()], onComplete, false);

      expect(onComplete).not.toHaveBeenCalled();
    });

    test("replaces the skeleton with the file card when the file arrives", () => {
      renderCard(
        [startPacket(), progressPacket(), makePacket(), endPacket()],
        jest.fn(),
        false
      );

      expect(
        screen.queryByTestId("document-generation-skeleton")
      ).not.toBeInTheDocument();
      expect(screen.getByText("24 KB")).toBeInTheDocument();
    });

    test("leaves nothing behind when the document tool errors out", () => {
      // The agent retries or explains the failure in its reply; a notice here
      // would interrupt that answer, once per rejected attempt.
      const { container } = renderCard(
        [
          startPacket(),
          endPacket({ status: "error", error: "Error: unsupported format" }),
        ],
        jest.fn(),
        false
      );

      expect(
        screen.queryByTestId("document-generation-skeleton")
      ).not.toBeInTheDocument();
      expect(container).toHaveTextContent("");
    });

    test("a retry after a rejected tool call clears the failure state", () => {
      renderCard(
        [
          startPacket(),
          endPacket({ status: "error", error: "Error: missing content" }),
          startPacket({ filename: "rapor", format: "pdf" }),
        ],
        jest.fn(),
        false
      );

      expect(
        screen.queryByText("The document could not be created.")
      ).not.toBeInTheDocument();
      expect(
        screen.getByTestId("document-generation-skeleton")
      ).toBeInTheDocument();
    });

    test("a file produced by the retry wins over the earlier failure", () => {
      renderCard(
        [
          startPacket(),
          endPacket({ status: "error", error: "Error: missing content" }),
          startPacket({ filename: "rapor", format: "pdf" }),
          makePacket(),
          endPacket(),
        ],
        jest.fn(),
        false
      );

      expect(
        screen.queryByText("The document could not be created.")
      ).not.toBeInTheDocument();
      expect(screen.getByText("rapor.pdf")).toBeInTheDocument();
    });

    test("stops showing the skeleton when the stream ends without a file", () => {
      const onComplete = jest.fn();
      renderCard([startPacket(), progressPacket()], onComplete, true);

      expect(
        screen.queryByTestId("document-generation-skeleton")
      ).not.toBeInTheDocument();
      expect(onComplete).toHaveBeenCalled();
    });
  });
});
