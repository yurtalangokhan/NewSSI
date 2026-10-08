import { render, screen } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";

import DocumentHitCard from "@/sections/knowledge-search/components/DocumentHitCard";
import EntityHitCard from "@/sections/knowledge-search/components/EntityHitCard";
import {
  documentHit,
  entityHit,
} from "@/sections/knowledge-search/components/__fixtures__/searchFixtures";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);

describe("DocumentHitCard", () => {
  it("shows the document, its location, and a highlighted passage", async () => {
    const user = userEvent.setup();
    const onOpen = jest.fn();
    render(
      <DocumentHitCard
        hit={documentHit}
        query="saklama süresi"
        selected={false}
        showKind
        onOpen={onOpen}
      />
    );

    const card = screen.getByRole("button", { name: /Tedarikçi Sözleşmesi/ });
    // The type tile shows the type icon (with the type as its tooltip), not text.
    const fileType = screen.getByTitle("PDF");
    expect(fileType.querySelector("svg")).toBeInTheDocument();
    expect(card).toHaveTextContent("Parça");
    expect(card).toHaveTextContent("Hukuk & Sözleşmeler");
    expect(card).toHaveTextContent("Sayfa 7");
    expect(card).toHaveTextContent("Madde 9");
    expect(screen.getByText("saklama")).toHaveProperty("tagName", "MARK");
    expect(screen.getByLabelText("Göreli alaka 1,00")).toBeInTheDocument();

    await user.click(card);
    expect(onOpen).toHaveBeenCalledWith(documentHit);
  });

  it("hides the kind tag outside hybrid search and marks selection", () => {
    render(
      <DocumentHitCard
        hit={documentHit}
        query="q"
        selected
        showKind={false}
        onOpen={jest.fn()}
      />
    );

    const card = screen.getByRole("button", { name: /Tedarikçi/ });
    expect(card).not.toHaveTextContent("Parça");
    expect(card).toHaveAttribute("aria-haspopup", "dialog");
    expect(card.firstElementChild).toHaveClass("bg-action-link-01");
  });

  it("falls back to an untitled label", () => {
    render(
      <DocumentHitCard
        hit={{
          ...documentHit,
          document: { ...documentHit.document!, source: null, fileType: null },
        }}
        query="q"
        selected={false}
        showKind={false}
        onOpen={jest.fn()}
      />
    );

    expect(screen.getByText("Adsız doküman")).toBeInTheDocument();
  });
});

describe("EntityHitCard", () => {
  it("shows the entity, its type, relations, and neighbors", async () => {
    const user = userEvent.setup();
    const onOpen = jest.fn();
    render(
      <EntityHitCard
        hit={entityHit}
        selected={false}
        showKind
        onOpen={onOpen}
      />
    );

    const card = screen.getByRole("button", {
      name: /Veri Saklama Politikası/,
    });
    expect(card).toHaveTextContent("Varlık");
    expect(card).toHaveTextContent("Policy");
    expect(card).toHaveTextContent("Eşleşti");
    expect(card).toHaveTextContent("Kurumsal Graph");
    expect(card).toHaveTextContent("6 komşu");
    expect(card).toHaveTextContent("SORUMLUSU");
    expect(card).toHaveTextContent("Veri Koruma Sorumlusu");

    await user.click(card);
    expect(onOpen).toHaveBeenCalledWith(entityHit);
  });

  it("shows incoming relations with an inverse arrow", () => {
    render(
      <EntityHitCard
        hit={{
          ...entityHit,
          entity: {
            ...entityHit.entity!,
            relations: [
              {
                type: "YÖNETİR",
                direction: "in",
                nodeId: "n3",
                nodeName: "Hukuk Departmanı",
                nodeLabel: "Department",
              },
            ],
          },
        }}
        selected={false}
        showKind={false}
        onOpen={jest.fn()}
      />
    );

    expect(screen.getByText("← YÖNETİR")).toBeInTheDocument();
    expect(screen.getByText("Hukuk Departmanı")).toBeInTheDocument();
  });
});
