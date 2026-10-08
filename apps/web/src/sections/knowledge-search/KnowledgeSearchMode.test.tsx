import { render, screen } from "@tests/setup/test-utils";

import KnowledgeSearchMode from "@/sections/knowledge-search/KnowledgeSearchMode";

let mockSearchSessionKey = 0;
jest.mock("@/providers/AppModeProvider", () => ({
  useAppMode: () => ({
    searchSessionKey: mockSearchSessionKey,
  }),
}));

let mounts = 0;
jest.mock("@/sections/knowledge-search/KnowledgeSearchView", () => {
  const { useEffect } = jest.requireActual("react");
  return function MockKnowledgeSearchView() {
    useEffect(() => {
      mounts += 1;
    }, []);
    return <p>search view</p>;
  };
});

beforeEach(() => {
  mockSearchSessionKey = 0;
  mounts = 0;
});

describe("KnowledgeSearchMode", () => {
  it("renders the search view", () => {
    render(<KnowledgeSearchMode />);

    expect(screen.getByText("search view")).toBeInTheDocument();
  });

  it("fades the screen in when the session switches to search", () => {
    const { container } = render(<KnowledgeSearchMode />);
    const root = container.firstElementChild;

    expect(root).toHaveClass("animate-in", "fade-in");
    // Reduced motion keeps the mode switch instantaneous.
    expect(root?.className).toContain("motion-reduce:animate-none");
  });

  it("starts a fresh search view for a new search session", () => {
    const { rerender } = render(<KnowledgeSearchMode />);
    expect(mounts).toBe(1);

    mockSearchSessionKey = 1;
    rerender(<KnowledgeSearchMode />);

    expect(mounts).toBe(2);
  });
});
