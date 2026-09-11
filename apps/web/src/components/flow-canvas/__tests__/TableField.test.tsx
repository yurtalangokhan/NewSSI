/**
 * TABLE cells honour their column's type.
 *
 * Before this every cell was a free-text box, which is how a mistyped Router
 * operator ("equal" instead of "equals") could reach a saved flow — and at run
 * time an unknown operator is silently false, so that route just never fired.
 * A dropdown makes the mistake unmakeable.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { TableField } from "../fields/TableField";
import type { InputField, TableColumn } from "../types/componentTemplate";

function field(columns: TableColumn[]): InputField {
  return {
    type: "table",
    display_name: "Rows",
    required: false,
    value: null,
    options: null,
    options_source: null,
    info: null,
    advanced: false,
    min: null,
    max: null,
    columns,
  } as unknown as InputField;
}

const OPERATOR_COLUMN: TableColumn = {
  name: "operator",
  display_name: "Operator",
  type: "options",
  options: ["equals", "contains"],
};

function renderField(
  columns: TableColumn[],
  rows: Record<string, unknown>[],
  onChange = jest.fn()
) {
  render(
    <TableField
      fieldKey="routes"
      field={field(columns)}
      value={rows}
      onChange={onChange}
      columns={columns}
    />
  );
  return onChange;
}

describe("TableField column types", () => {
  it("renders an options column as a select, not a text box", () => {
    renderField([OPERATOR_COLUMN], [{ operator: "equals" }]);
    expect(screen.getByTestId("table-cell-operator-0")).toBeInTheDocument();
    // A free-text box would accept anything; a select only its own options.
    expect(screen.queryByDisplayValue("equals")).toBeNull();
  });

  it("offers exactly the column's options", () => {
    renderField([OPERATOR_COLUMN], [{ operator: "equals" }]);
    fireEvent.click(screen.getByTestId("table-cell-operator-0"));
    // Radix renders an option's text in both the popup and a hidden native
    // select, so more than one node is expected.
    expect(screen.getAllByText("contains").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("starts_with")).toHaveLength(0);
  });

  it("writes a cell back to that row only", () => {
    /* Exercised through the boolean column: Radix's select does not complete a
     * selection under jsdom's synthetic clicks, and the behaviour under test —
     * that a cell edit touches one row — is the same for every column type. */
    const onChange = renderField(
      [{ name: "multiple", display_name: "As list", type: "bool" }],
      [{ multiple: false }, { multiple: false }]
    );
    fireEvent.click(screen.getAllByRole("switch")[1]!);
    expect(onChange).toHaveBeenCalledWith([
      { multiple: false },
      { multiple: true },
    ]);
  });

  it("renders a boolean column as a switch", () => {
    renderField(
      [{ name: "multiple", display_name: "As list", type: "bool" }],
      [{ multiple: false }]
    );
    expect(screen.getByRole("switch")).toBeInTheDocument();
  });

  it("writes a boolean back as a real boolean, not a string", () => {
    const onChange = renderField(
      [{ name: "multiple", display_name: "As list", type: "bool" }],
      [{ multiple: false }]
    );
    fireEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith([{ multiple: true }]);
  });

  it("still renders an unconstrained column as free text", () => {
    renderField(
      [{ name: "match_text", display_name: "Match text", type: "str" }],
      [{ match_text: "merhaba" }]
    );
    expect(screen.getByDisplayValue("merhaba")).toBeInTheDocument();
  });

  it("uses the column's display name in the header", () => {
    renderField([OPERATOR_COLUMN], [{ operator: "equals" }]);
    expect(screen.getByText("Operator")).toBeInTheDocument();
  });

  it("gives a new row a value of the right shape per column", () => {
    const onChange = renderField(
      [
        OPERATOR_COLUMN,
        { name: "multiple", display_name: "As list", type: "bool" },
      ],
      []
    );
    fireEvent.click(screen.getByText(/add row/i));
    expect(onChange).toHaveBeenCalledWith([
      { operator: "equals", multiple: false },
    ]);
  });

  it("falls back to the row keys when no column metadata is given", () => {
    render(
      <TableField
        fieldKey="routes"
        field={field([])}
        value={[{ anything: "x" }]}
        onChange={jest.fn()}
      />
    );
    expect(screen.getByDisplayValue("x")).toBeInTheDocument();
  });
});
