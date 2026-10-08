/**
 * @jest-environment jsdom
 */
import { DEFAULT_COLUMN_CSS_PX, measureColumnCssPx } from "./column";

function stubOffsetWidth(width: number) {
  return jest
    .spyOn(HTMLElement.prototype, "offsetWidth", "get")
    .mockReturnValue(width);
}

describe("measureColumnCssPx", () => {
  afterEach(() => {
    jest.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("resolves the app's message-column width by measuring the CSS variable", () => {
    const parent = document.createElement("div");
    const canvas = document.createElement("canvas");
    parent.append(canvas);
    document.body.append(parent);
    stubOffsetWidth(840);

    expect(measureColumnCssPx(canvas)).toBe(840);
  });

  it("uses the measured width even when the container is narrower than the variable", () => {
    const parent = document.createElement("div");
    const canvas = document.createElement("canvas");
    parent.append(canvas);
    document.body.append(parent);
    stubOffsetWidth(610);

    expect(measureColumnCssPx(canvas)).toBe(610);
  });

  it("falls back to the design width when the browser reports nothing", () => {
    const canvas = document.createElement("canvas");
    document.body.append(canvas);
    stubOffsetWidth(0);

    expect(measureColumnCssPx(canvas)).toBe(DEFAULT_COLUMN_CSS_PX);
  });

  it("leaves no measuring element behind", () => {
    const parent = document.createElement("div");
    const canvas = document.createElement("canvas");
    parent.append(canvas);
    document.body.append(parent);
    stubOffsetWidth(840);

    measureColumnCssPx(canvas);

    expect(parent.children).toHaveLength(1);
  });
});
