import { render, screen } from "@testing-library/react";
import { LazyCodeEditor } from "@/sections/document-panel/LazyCodeEditor";

jest.mock("@/sections/document-panel/CodeEditor", () => ({
  CodeEditor: ({ ariaLabel }: { ariaLabel: string }) => (
    <div aria-label={ariaLabel} data-testid="code-editor" />
  ),
}));

it("shows a skeleton first and then loads the editor on demand", async () => {
  render(<LazyCodeEditor value="# A" ariaLabel="source" />);

  expect(screen.getByTestId("code-editor-loading")).toBeInTheDocument();
  expect(await screen.findByTestId("code-editor")).toBeInTheDocument();
  expect(screen.queryByTestId("code-editor-loading")).not.toBeInTheDocument();
});
