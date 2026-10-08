import { render, screen } from "@testing-library/react";
import Actionbar from "./Actionbar";

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

describe("Actionbar", () => {
  it("shows the add button by default", () => {
    render(
      <Actionbar hasActions onAddAction={jest.fn()} buttonText="Add server" />
    );

    expect(
      screen.getByRole("button", { name: "Add server" })
    ).toBeInTheDocument();
  });

  it("hides the add button when the caller is not allowed to add", () => {
    render(
      <Actionbar
        hasActions
        onAddAction={jest.fn()}
        buttonText="Add server"
        canAddAction={false}
      />
    );

    expect(
      screen.queryByRole("button", { name: "Add server" })
    ).not.toBeInTheDocument();
  });

  it("still renders the search field when the add button is hidden", () => {
    render(
      <Actionbar
        hasActions
        onAddAction={jest.fn()}
        searchQuery=""
        onSearchQueryChange={jest.fn()}
        canAddAction={false}
      />
    );

    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });
});
