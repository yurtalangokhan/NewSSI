import { render, screen } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";
import { GeneratedFileRenderer } from "@/app/app/message/messageComponents/renderers/GeneratedFileRenderer";
import { RenderType } from "@/app/app/message/messageComponents/interfaces";
import {
  GeneratedFilePacket,
  PacketType,
} from "@/app/app/services/streamingModels";
import { MinimalOnyxDocument } from "@/lib/search/interfaces";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
  }),
}));

const textViewModalSpy = jest.fn();
jest.mock("@/sections/modals/TextViewModal", () => ({
  __esModule: true,
  default: (props: { presentingDocument: MinimalOnyxDocument; onClose: () => void }) => {
    textViewModalSpy(props);
    return <div data-testid="text-view-modal">preview open</div>;
  },
}));

function makePacket(
  overrides: Partial<GeneratedFilePacket["obj"]> = {}
): GeneratedFilePacket {
  return {
    placement: { turn_index: 0, tab_index: 0 },
    obj: {
      type: PacketType.GENERATED_FILE,
      file_id: "abc123",
      filename: "rapor.pdf",
      mime_type: "application/pdf",
      size_bytes: 24576,
      download_url: "/api/chat/file/abc123?download=1",
      ...overrides,
    },
  };
}

function renderCard(packets: GeneratedFilePacket[], onComplete = jest.fn()) {
  return render(
    <GeneratedFileRenderer
      packets={packets}
      state={{}}
      onComplete={onComplete}
      renderType={RenderType.FULL}
      animate={false}
      stopPacketSeen={true}
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
      placement: { turn_index: 0, tab_index: 0 },
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
});
