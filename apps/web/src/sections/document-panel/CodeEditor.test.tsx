import { act, render } from "@testing-library/react";
import { EditorView } from "@codemirror/view";
import { CodeEditor } from "@/sections/document-panel/CodeEditor";

beforeAll(() => {
  // jsdom has no layout; CodeMirror only needs these to exist.
  const rects = () =>
    Object.assign([], { item: () => null }) as unknown as DOMRectList;
  Range.prototype.getClientRects = rects;
  Range.prototype.getBoundingClientRect = () => new DOMRect();
});

const viewOf = (container: HTMLElement) =>
  EditorView.findFromDOM(container.querySelector(".cm-editor") as HTMLElement)!;

it("renders the value and reports user edits", () => {
  const onChange = jest.fn();
  const { container } = render(
    <CodeEditor value={"# A\nb"} onChange={onChange} ariaLabel="src" />
  );

  expect(container.querySelector(".cm-content")).toHaveAttribute(
    "aria-label",
    "src"
  );
  act(() => viewOf(container).dispatch({ changes: { from: 0, insert: "x" } }));
  expect(onChange).toHaveBeenLastCalledWith("x# A\nb");
});

it("applies external values without echoing them", () => {
  const onChange = jest.fn();
  const { container, rerender } = render(
    <CodeEditor value="one" onChange={onChange} ariaLabel="src" />
  );

  rerender(<CodeEditor value="two" onChange={onChange} ariaLabel="src" />);
  expect(viewOf(container).state.doc.toString()).toBe("two");
  expect(onChange).not.toHaveBeenCalled();
});

it("highlights diagnostic lines", () => {
  const { container, rerender } = render(
    <CodeEditor value={"a\nb\nc"} ariaLabel="src" />
  );
  rerender(
    <CodeEditor value={"a\nb\nc"} ariaLabel="src" highlightLines={[2, 9]} />
  );

  const lines = container.querySelectorAll(".cm-diagnostic-line");
  expect(lines).toHaveLength(1);
  expect(lines[0]).toHaveTextContent("b");
});

it("shows a unified merge view against the original", () => {
  const { container } = render(
    <CodeEditor
      value={"a\nB\nc"}
      mergeOriginal={"a\nb\nc"}
      readOnly
      ariaLabel="diff"
    />
  );

  expect(container.querySelector(".cm-changedLine")).not.toBeNull();
  expect(container.querySelector(".cm-deletedChunk")).not.toBeNull();
  expect(viewOf(container).state.readOnly).toBe(true);
});
