import { render, screen } from "@tests/setup/test-utils";
import userEvent from "@testing-library/user-event";

import SearchBox from "@/sections/knowledge-search/components/SearchBox";
import type { RetrievalKind } from "@/lib/api/domains/knowledge/knowledge-search-types";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);

function renderBox(
  overrides: Partial<React.ComponentProps<typeof SearchBox>> = {}
) {
  const props = {
    value: "",
    kind: "hybrid" as RetrievalKind,
    onChange: jest.fn(),
    onSubmit: jest.fn(),
    onClear: jest.fn(),
    onKindChange: jest.fn(),
    ...overrides,
  };
  render(<SearchBox {...props} />);
  return props;
}

describe("SearchBox", () => {
  it("edits and submits the query", async () => {
    const user = userEvent.setup();
    const props = renderBox({ value: "saklama" });

    const input = screen.getByRole("searchbox", { name: "Arama sorgusu" });
    expect(input).toHaveValue("saklama");
    await user.type(input, "x");
    expect(props.onChange).toHaveBeenLastCalledWith("saklamax");

    await user.type(input, "{Enter}");
    expect(props.onSubmit).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Ara" }));
    expect(props.onSubmit).toHaveBeenCalledTimes(2);
  });

  it("keeps every control in a single row", () => {
    renderBox({ value: "saklama" });

    // globals.css turns every <form> into a column, so the row layout depends
    // on this utility overriding that base rule.
    expect(screen.getByRole("search")).toHaveClass("flex-row");
  });

  it("shows progress and blocks a second submit while a search runs", () => {
    renderBox({ value: "saklama", busy: true });

    expect(screen.getByRole("search")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Ara" })).toBeDisabled();
  });

  it("reports an idle search box", () => {
    renderBox({ value: "saklama" });

    expect(screen.getByRole("search")).toHaveAttribute("aria-busy", "false");
    expect(screen.getByRole("button", { name: "Ara" })).toBeEnabled();
  });

  it("disables submit for a blank query", () => {
    renderBox({ value: "  " });

    expect(screen.getByRole("button", { name: "Ara" })).toBeDisabled();
  });

  it("clears only when there is text", () => {
    const empty = renderBox();
    expect(
      screen.queryByRole("button", { name: "Aramayı temizle" })
    ).not.toBeInTheDocument();
    expect(empty.onClear).not.toHaveBeenCalled();
  });

  it("clears the query", async () => {
    const user = userEvent.setup();
    const props = renderBox({ value: "q" });

    await user.click(screen.getByRole("button", { name: "Aramayı temizle" }));

    expect(props.onClear).toHaveBeenCalledTimes(1);
  });

  it("switches the retrieval kind", async () => {
    const user = userEvent.setup();
    const props = renderBox({ kind: "hybrid" });

    const group = screen.getByRole("group", { name: "Arama türü" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hibrit" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByRole("button", { name: "Graph" })).toHaveAttribute(
      "aria-pressed",
      "false"
    );

    await user.click(screen.getByRole("button", { name: "Doküman" }));

    expect(props.onKindChange).toHaveBeenCalledWith("vector");
  });

  it("disables graph search when it is unavailable", () => {
    renderBox({ graphDisabled: true });

    expect(screen.getByRole("button", { name: "Graph" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Hibrit" })).toBeEnabled();
  });

  it("focuses the input with the slash shortcut", async () => {
    const user = userEvent.setup();
    renderBox({ shortcut: true });

    await user.keyboard("/");

    expect(screen.getByRole("searchbox")).toHaveFocus();
  });

  it("ignores the slash shortcut while typing elsewhere", async () => {
    const user = userEvent.setup();
    render(
      <>
        <input aria-label="other" />
        <SearchBox
          value=""
          kind="hybrid"
          onChange={jest.fn()}
          onSubmit={jest.fn()}
          onClear={jest.fn()}
          onKindChange={jest.fn()}
          shortcut
        />
      </>
    );

    await user.click(screen.getByLabelText("other"));
    await user.keyboard("/");

    expect(screen.getByLabelText("other")).toHaveFocus();
  });
});
