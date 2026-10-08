import { render, screen, setupUser, within } from "@tests/setup/test-utils";
import {
  RenderType,
  type RendererResult,
} from "@/app/app/message/messageComponents/interfaces";
import { KnowledgeRetrievalRenderer } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/KnowledgeRetrievalRenderer";
import {
  PacketType,
  type CustomToolPacket,
  type Packet,
} from "@/lib/api/domains/chat/streaming-types";
import {
  documentEvidence,
  graphEvidence,
  knowledgePackets,
} from "@/app/app/message/messageComponents/timeline/renderers/knowledge/__tests__/fixtures";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);
// jsdom cannot draw on canvas; graph nodes become buttons named "name, label".
jest.mock("@/refresh-components/knowledge-graph/KnowledgeForceGraph", () =>
  jest.requireActual(
    "@/refresh-components/knowledge-graph/__fixtures__/knowledgeForceGraphStub"
  )
);

function renderCard(
  packets: Packet[],
  onComplete = jest.fn(),
  renderType: RenderType = RenderType.FULL
) {
  return render(
    <KnowledgeRetrievalRenderer
      packets={packets as CustomToolPacket[]}
      state={{}}
      onComplete={onComplete}
      renderType={renderType}
      animate={false}
      stopPacketSeen
    >
      {(results) => (
        <>
          {results.map((result, index) => (
            <section key={index}>
              <header>{result.status}</header>
              {result.content}
            </section>
          ))}
        </>
      )}
    </KnowledgeRetrievalRenderer>
  );
}

describe("KnowledgeRetrievalRenderer — document search", () => {
  it("summarises the search and lists every chunk with its source", () => {
    const onComplete = jest.fn();
    renderCard(knowledgePackets(documentEvidence), onComplete);

    expect(screen.getByText("Belgelerde arandı")).toBeInTheDocument();
    expect(
      screen.getByText("2 parça · 2 belge · İK Politikaları · 420ms")
    ).toBeInTheDocument();
    expect(screen.getByText("İzin Yönetmeliği 2026")).toBeInTheDocument();
    expect(screen.getByText("İK Süreç El Kitabı")).toBeInTheDocument();
    expect(screen.getByText("0,89")).toBeInTheDocument();
    expect(onComplete).toHaveBeenCalled();
  });

  it("highlights the query's words in chunk previews", () => {
    renderCard(knowledgePackets(documentEvidence));

    const marked = screen
      .getAllByText(/./, { selector: "mark" })
      .map((mark) => mark.textContent);
    expect(marked).toEqual(expect.arrayContaining(["yıllık", "izin", "onay"]));
  });

  it("opens the full chunk in a side panel and steps through chunks", async () => {
    const user = setupUser();
    renderCard(knowledgePackets(documentEvidence));

    await user.click(screen.getByText("İzin Yönetmeliği 2026"));
    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText("Parça 1 / 2")).toBeInTheDocument();
    expect(within(panel).getByText("chk_9f2a41")).toBeInTheDocument();
    expect(
      within(panel).getByText("Sayfa 7 · §4.2 · skor 0,89")
    ).toBeInTheDocument();

    await user.click(
      within(panel).getByRole("button", { name: "Sonraki parça" })
    );
    expect(within(panel).getByText("Parça 2 / 2")).toBeInTheDocument();

    await user.keyboard("{ArrowDown}");
    expect(within(panel).getByText("Parça 1 / 2")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the exact text the model received on request", async () => {
    const user = setupUser();
    renderCard(knowledgePackets(documentEvidence));

    await user.click(
      screen.getByRole("button", { name: "Modelin gördüğü metni göster" })
    );

    expect(
      screen.getByText(/\[1\] \(İzin Yönetmeliği 2026\.pdf\)/)
    ).toBeInTheDocument();
  });

  it("says so when the search found nothing", () => {
    renderCard(knowledgePackets({ ...documentEvidence, chunks: [] }));

    expect(
      screen.getByText("İlgili bir sonuç bulunamadı.")
    ).toBeInTheDocument();
  });

  it("says so when the evidence could not be loaded", () => {
    renderCard(knowledgePackets(null));

    expect(
      screen.getByText("Bu aramanın ayrıntılarına artık ulaşılamıyor.")
    ).toBeInTheDocument();
  });

  it("shows the tool's own text when it returned no evidence", () => {
    const [start] = knowledgePackets(documentEvidence);
    renderCard([
      start!,
      {
        placement: { turn_index: 0 },
        obj: {
          type: "custom_tool_delta",
          tool_name: "database_search",
          response_type: "tool_result",
          data: "Bilgi erişimi başarısız oldu.",
          call_id: "call-1",
        },
      } as Packet,
    ]);

    expect(
      screen.getByText("Bilgi erişimi başarısız oldu.")
    ).toBeInTheDocument();
  });
});

describe("KnowledgeRetrievalRenderer — graph search", () => {
  const graphLabel = "Bu aramanın kullandığı varlıklar ve ilişkiler";

  it("summarises entities, relations, and direct matches", () => {
    renderCard(knowledgePackets(graphEvidence, "graph_search"));

    expect(screen.getByText("Bilgi grafında arandı")).toBeInTheDocument();
    expect(
      screen.getByText(
        "3 varlık · 2 ilişki · 2 doğrudan eşleşme · İK Bilgi Grafı · 310ms"
      )
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: graphLabel })).toBeInTheDocument();
  });

  it("ranks the direct matches and details the strongest by default", () => {
    renderCard(knowledgePackets(graphEvidence, "graph_search"));

    const matches = within(
      screen.getByRole("list", { name: "En güçlü eşleşmeler" })
    ).getAllByRole("button");
    expect(matches.map((row) => row.textContent)).toEqual([
      expect.stringContaining("Yıllık İzin Devri"),
      expect.stringContaining("Birim Yöneticisi"),
    ]);
    expect(
      screen.getByText("Sorguyla doğrudan eşleşti · RRF 0,0098")
    ).toBeInTheDocument();
    expect(screen.getByText("15 Aralık")).toBeInTheDocument();
  });

  it("details a match picked from the ranking", async () => {
    const user = setupUser();
    renderCard(knowledgePackets(graphEvidence, "graph_search"));

    const matches = screen.getByRole("list", { name: "En güçlü eşleşmeler" });
    const second = within(matches).getByRole("button", {
      name: /Birim Yöneticisi/,
    });
    await user.click(second);

    expect(second).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("heading", { name: "Birim Yöneticisi" })
    ).toBeInTheDocument();
  });

  it("details an entity picked in the graph, with only its relations", async () => {
    const user = setupUser();
    renderCard(knowledgePackets(graphEvidence, "graph_search"));

    screen.getByRole("button", { name: "İK Direktörlüğü, Department" }).focus();
    await user.keyboard("{Enter}");

    expect(screen.getByText("Komşuluktan genişletildi")).toBeInTheDocument();
    const relations = within(screen.getByRole("list", { name: "İlişkiler" }));
    expect(relations.getAllByRole("button")).toHaveLength(1);
    expect(
      relations.getByRole("button", { name: /OWNED_BY/ })
    ).toBeInTheDocument();
  });

  it("switches to the list of every relation", async () => {
    const user = setupUser();
    renderCard(knowledgePackets(graphEvidence, "graph_search"));

    await user.click(screen.getByRole("button", { name: "Liste" }));

    expect(
      screen.queryByRole("img", { name: graphLabel })
    ).not.toBeInTheDocument();
    const all = within(screen.getByRole("list", { name: "Tüm ilişkiler" }));
    expect(all.getAllByRole("button")).toHaveLength(2);
  });
});

describe("KnowledgeRetrievalRenderer — selected state", () => {
  const rankingLabel = "En güçlü eşleşmeler";

  it("marks the strongest match as the selected ranking row", () => {
    renderCard(knowledgePackets(graphEvidence, "graph_search"));

    const [first, second] = within(
      screen.getByRole("list", { name: rankingLabel })
    ).getAllByRole("button");
    expect(first).toHaveAttribute("aria-pressed", "true");
    expect(first).toHaveAttribute("data-selected", "true");
    // Only a heavy select row paints a selected background behind its text.
    expect(first).toHaveAttribute("data-interactive-base-prominence", "heavy");
    expect(second).toHaveAttribute("aria-pressed", "false");
  });

  it("marks the picked relation row as selected", async () => {
    const user = setupUser();
    renderCard(knowledgePackets(graphEvidence, "graph_search"));

    await user.click(screen.getByRole("button", { name: "Liste" }));
    const all = within(screen.getByRole("list", { name: "Tüm ilişkiler" }));
    const [required, owned] = all.getAllByRole("button");
    expect(required).toHaveAttribute("aria-pressed", "false");

    await user.click(required!);

    expect(required).toHaveAttribute("aria-pressed", "true");
    expect(required).toHaveAttribute("data-selected", "true");
    expect(required).toHaveAttribute(
      "data-interactive-base-prominence",
      "heavy"
    );
    expect(owned).toHaveAttribute("aria-pressed", "false");
  });

  it("tells assistive technology which view is on", async () => {
    const user = setupUser();
    renderCard(knowledgePackets(graphEvidence, "graph_search"));

    const graphView = screen.getByRole("button", { name: "Graf" });
    const listView = screen.getByRole("button", { name: "Liste" });
    expect(graphView).toHaveAttribute("aria-pressed", "true");
    expect(listView).toHaveAttribute("aria-pressed", "false");

    await user.click(listView);

    expect(graphView).toHaveAttribute("aria-pressed", "false");
    expect(listView).toHaveAttribute("aria-pressed", "true");
  });

  it("marks the chunk whose panel is open", async () => {
    const user = setupUser();
    renderCard(knowledgePackets(documentEvidence));

    const row = screen.getByText("İzin Yönetmeliği 2026").closest("button")!;
    expect(row).toHaveAttribute("aria-pressed", "false");

    await user.click(row);

    expect(row).toHaveAttribute("aria-pressed", "true");
  });
});

describe("KnowledgeRetrievalRenderer — entity details", () => {
  it("hides the ranking scores and shows an empty property as a dash", () => {
    renderCard(knowledgePackets(graphEvidence, "graph_search"));

    expect(screen.getByText("son tarih")).toBeInTheDocument();
    expect(screen.queryByText("rrf score")).not.toBeInTheDocument();
    expect(screen.queryByText("bm25 score")).not.toBeInTheDocument();
    expect(screen.getByText("sorumlu")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("KnowledgeRetrievalRenderer — render types and completion", () => {
  function firstResult(renderType: RenderType) {
    let captured: RendererResult[] = [];
    render(
      <KnowledgeRetrievalRenderer
        packets={knowledgePackets(documentEvidence) as CustomToolPacket[]}
        state={{}}
        onComplete={jest.fn()}
        renderType={renderType}
        animate={false}
        stopPacketSeen
      >
        {(results) => {
          captured = results;
          return <></>;
        }}
      </KnowledgeRetrievalRenderer>
    );
    return captured[0]!;
  }

  it("shows no body in compact mode", () => {
    const result = firstResult(RenderType.COMPACT);

    expect(result.timelineLayout).toBe("timeline");
    expect(result.icon).not.toBeNull();
    const { container } = render(<>{result.content}</>);
    expect(container).toBeEmptyDOMElement();
  });

  it.each([RenderType.HIGHLIGHT, RenderType.INLINE])(
    "reduces %s to the one-line summary",
    (renderType) => {
      const result = firstResult(renderType);

      expect(result.icon).toBeNull();
      expect(result.status).toBeNull();
      expect(result.timelineLayout).toBe("content");
      render(<>{result.content}</>);
      expect(screen.getByText("Belgelerde arandı")).toBeInTheDocument();
      expect(
        screen.queryByText("İzin Yönetmeliği 2026")
      ).not.toBeInTheDocument();
    }
  );

  it("completes when the section ends even though a call never answered", () => {
    const [start] = knowledgePackets(documentEvidence);
    const onComplete = jest.fn();

    renderCard([start!], onComplete);
    expect(onComplete).not.toHaveBeenCalled();

    onComplete.mockClear();
    renderCard(
      [
        start!,
        {
          placement: { turn_index: 0, tab_index: 0 },
          obj: { type: PacketType.SECTION_END },
        } as Packet,
      ],
      onComplete
    );
    expect(onComplete).toHaveBeenCalled();
  });

  it("completes when the turn errors", () => {
    const [start] = knowledgePackets(documentEvidence);
    const onComplete = jest.fn();

    renderCard(
      [
        start!,
        {
          placement: { turn_index: 0, tab_index: 0 },
          obj: { type: PacketType.ERROR, message: "boom" },
        } as unknown as Packet,
      ],
      onComplete
    );

    expect(onComplete).toHaveBeenCalled();
  });
});
