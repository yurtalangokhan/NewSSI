import { render, screen, within } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";

import SearchLanding from "@/sections/knowledge-search/components/SearchLanding";
import { sources } from "@/sections/knowledge-search/components/__fixtures__/searchFixtures";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);

function renderLanding(
  overrides: Partial<React.ComponentProps<typeof SearchLanding>> = {}
) {
  const props: React.ComponentProps<typeof SearchLanding> = {
    draft: "",
    kind: "hybrid",
    onDraftChange: jest.fn(),
    onSubmit: jest.fn(),
    onClear: jest.fn(),
    onKindChange: jest.fn(),
    graphDisabled: false,
    sources,
    sourcesLoading: false,
    sourcesError: undefined,
    selectedCollectionIds: [],
    onCollectionToggle: jest.fn(),
    recentSearches: ["tedarikçi saklama süresi", "KVKK"],
    onRecentSelect: jest.fn(),
    onClearRecent: jest.fn(),
    ...overrides,
  };
  render(<SearchLanding {...props} />);
  return props;
}

describe("SearchLanding", () => {
  it("introduces the search and focuses the query box", () => {
    renderLanding();

    expect(
      screen.getByRole("heading", { name: "Bilgi tabanında ara" })
    ).toBeInTheDocument();
    expect(screen.getByRole("searchbox")).toHaveFocus();
  });

  it("lists searchable sources with their type and scopes the search", async () => {
    const user = userEvent.setup();
    const props = renderLanding({ selectedCollectionIds: ["kg"] });

    const list = screen.getByRole("group", { name: "Aranabilir kaynaklar" });
    const drive = within(list).getByRole("button", { name: /Satın Alma/ });
    expect(drive).toHaveTextContent("Connector");
    expect(drive).toHaveTextContent("Senkron");
    expect(
      within(list).getByRole("button", { name: /Kurumsal Graph/ })
    ).toHaveAttribute("aria-pressed", "true");

    await user.click(drive);
    expect(props.onCollectionToggle).toHaveBeenCalledWith("drive");
  });

  it("counts the selected sources", () => {
    renderLanding({ selectedCollectionIds: ["kg", "drive"] });

    expect(screen.getByText("2 kaynak seçili")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Kurumsal Graph/ })
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("paints selected and unselected sources differently", () => {
    renderLanding({ selectedCollectionIds: ["drive"] });

    expect(
      screen.getByRole("button", { name: /Satın Alma/ }).firstElementChild
    ).toHaveClass("bg-action-link-01");
    expect(
      screen.getByRole("button", { name: /Kurumsal Graph/ }).firstElementChild
    ).toHaveClass("bg-background-neutral-01");
  });

  it("runs and clears recent searches", async () => {
    const user = userEvent.setup();
    const props = renderLanding();

    await user.click(screen.getByRole("button", { name: "KVKK" }));
    expect(props.onRecentSelect).toHaveBeenCalledWith("KVKK");

    await user.click(screen.getByRole("button", { name: "Temizle" }));
    expect(props.onClearRecent).toHaveBeenCalled();
  });

  it("hides recent searches when there are none", () => {
    renderLanding({ recentSearches: [] });

    expect(screen.queryByText("Son aramalar")).not.toBeInTheDocument();
  });

  it("explains how to add sources when none exist", () => {
    renderLanding({ sources: [] });

    expect(screen.getByText("Henüz aranabilir kaynak yok")).toBeInTheDocument();
  });

  it("reports sources that are still loading", () => {
    renderLanding({ sources: [], sourcesLoading: true });

    expect(screen.getByRole("status")).toHaveTextContent(
      "Kaynaklar yükleniyor..."
    );
  });

  it("reports sources that failed to load", () => {
    renderLanding({ sources: [], sourcesError: new Error("down") });

    expect(screen.getByText("Kaynaklar yüklenemedi.")).toBeInTheDocument();
  });

  it("lists recent searches above the sources", () => {
    renderLanding();

    const recent = screen.getByRole("heading", { name: "Son aramalar" });
    const sources = screen.getByRole("heading", {
      name: "Aranabilir kaynaklar",
    });

    expect(
      recent.compareDocumentPosition(sources) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("scrolls a long source list instead of growing the panel", () => {
    renderLanding();

    // The fade container carries the scroll region; the grid keeps the group.
    expect(
      screen.getByRole("group", { name: "Aranabilir kaynaklar" }).parentElement
    ).toHaveClass("overflow-y-auto");
  });

  it("filters the sources by name", async () => {
    const user = userEvent.setup();
    renderLanding();

    await user.type(screen.getByLabelText("Kaynaklarda ara"), "kurumsal");

    expect(
      screen.getByRole("button", { name: /Kurumsal Graph/ })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Satın Alma/ })
    ).not.toBeInTheDocument();
  });

  it("reports sources that do not match the filter", async () => {
    const user = userEvent.setup();
    renderLanding();

    await user.type(screen.getByLabelText("Kaynaklarda ara"), "zzz");

    expect(screen.getByText("Eşleşen kaynak yok.")).toBeInTheDocument();
  });
});
