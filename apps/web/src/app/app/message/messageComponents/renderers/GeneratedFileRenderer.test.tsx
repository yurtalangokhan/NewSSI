import { render, screen } from "@tests/setup/test-utils";
import { GeneratedFileRenderer } from "@/app/app/message/messageComponents/renderers/GeneratedFileRenderer";
import { RenderType } from "@/app/app/message/messageComponents/interfaces";
import {
  GeneratedFilePacket,
  PacketType,
} from "@/app/app/services/streamingModels";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (_key: string, fallback?: string) => fallback ?? _key,
  }),
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

describe("GeneratedFileRenderer", () => {
  test("renders filename, human-readable size, and a download link", () => {
    render(
      <GeneratedFileRenderer
        packets={[makePacket()]}
        state={{}}
        onComplete={jest.fn()}
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

    expect(screen.getByText("rapor.pdf")).toBeInTheDocument();
    expect(screen.getByText("24 KB")).toBeInTheDocument();

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/api/chat/file/abc123?download=1");
  });

  test("finds the file packet even when a trailing SECTION_END packet is appended", () => {
    // packetProcessor.ts appends a synthetic SECTION_END to the group once the
    // turn closes — the real-world shape is never a single lone packet.
    const sectionEndPacket = {
      placement: { turn_index: 0, tab_index: 0 },
      obj: { type: PacketType.SECTION_END },
    } as unknown as GeneratedFilePacket;

    render(
      <GeneratedFileRenderer
        packets={[makePacket(), sectionEndPacket]}
        state={{}}
        onComplete={jest.fn()}
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

    expect(screen.getByText("rapor.pdf")).toBeInTheDocument();
    expect(screen.queryByText("Unknown")).not.toBeInTheDocument();

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/api/chat/file/abc123?download=1");
  });

  test("calls onComplete immediately since the file is already fully known", () => {
    const onComplete = jest.fn();

    render(
      <GeneratedFileRenderer
        packets={[makePacket()]}
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

    expect(onComplete).toHaveBeenCalledTimes(1);
  });
});
