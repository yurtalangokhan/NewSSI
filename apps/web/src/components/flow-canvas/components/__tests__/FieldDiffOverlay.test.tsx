import { fireEvent, render, screen } from "@testing-library/react";
import { FieldDiffOverlay } from "../FieldDiffOverlay";

describe("FieldDiffOverlay", () => {
  it("shows a word-level diff with the old text struck through and the new text highlighted", () => {
    render(
      <FieldDiffOverlay
        field={{
          label: "Chatbot.system_prompt",
          oldValue: "Be helpful",
          newValue: "Be helpful and kind",
        }}
        onClose={jest.fn()}
      />
    );
    const overlay = screen.getByTestId("field-diff-overlay");
    expect(overlay).toHaveTextContent("Be helpful");
    expect(overlay).toHaveTextContent("and kind");
    expect(overlay).toHaveTextContent("Chatbot.system_prompt");
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = jest.fn();
    render(
      <FieldDiffOverlay
        field={{ label: "field", oldValue: "a", newValue: "b" }}
        onClose={onClose}
      />
    );
    fireEvent.click(screen.getByTestId("field-diff-overlay-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders an object value as JSON rather than [object Object]", () => {
    render(
      <FieldDiffOverlay
        field={{
          label: "table.routes",
          oldValue: [{ condition: "x" }],
          newValue: [{ condition: "y" }],
        }}
        onClose={jest.fn()}
      />
    );
    expect(screen.getByTestId("field-diff-overlay")).toHaveTextContent(
      '"condition"'
    );
  });
});
