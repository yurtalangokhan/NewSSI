/**
 * Tests for ComponentSidebar. `useComponentTemplates` (SWR) is mocked
 * directly — the real proxy route doesn't exist yet (Task 28), so this
 * task develops and tests against a fixture rather than a live fetch, per
 * the brief.
 *
 * Brief: .tmp/flow-canvas-task-25-brief.md
 */

import { fireEvent, render, screen } from "@testing-library/react";
import type { GroupedComponentTemplates } from "../types/componentTemplate";

const mockUseComponentTemplates = jest.fn();
jest.mock("../hooks/useComponentTemplates", () => ({
  useComponentTemplates: () => mockUseComponentTemplates(),
}));

import { ComponentSidebar } from "../components/ComponentSidebar";

function template(
  type: string,
  category: string,
  display_name: string,
  description = ""
) {
  return {
    type,
    category,
    display_name,
    description,
    icon: null,
    template_version: 1,
    lifecycle: "stable" as const,
    kind: "execution" as const,
    inputs: {},
    handles: { inputs: [], outputs: [] },
  };
}

const FIXTURE: GroupedComponentTemplates = {
  core: [
    template("ChatInput", "core", "Chat Input", "Accepts a user message"),
    template("ChatOutput", "core", "Chat Output"),
  ],
  agents: [template("ZeroShotAgent", "agents", "Zero-Shot Agent")],
};

beforeEach(() => {
  window.localStorage.clear();
  mockUseComponentTemplates.mockReset();
});

describe("ComponentSidebar — 25.1, server-side grouping used as-is", () => {
  it("renders categories exactly as returned by the API", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: FIXTURE,
      isLoading: false,
      error: undefined,
    });

    render(<ComponentSidebar />);

    expect(screen.getByTestId("sidebar-category-core")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-category-agents")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-item-ChatInput")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-item-ChatOutput")).toBeInTheDocument();
    expect(
      screen.getByTestId("sidebar-item-ZeroShotAgent")
    ).toBeInTheDocument();
  });
});

describe("ComponentSidebar — 25.4, empty state", () => {
  it("renders an empty state when nothing matches the search", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: FIXTURE,
      isLoading: false,
      error: undefined,
    });

    render(<ComponentSidebar />);
    fireEvent.change(screen.getByLabelText("Search components"), {
      target: { value: "nonexistent-xyz" },
    });

    expect(screen.getByText("No components found")).toBeInTheDocument();
    expect(
      screen.queryByTestId("sidebar-item-ChatInput")
    ).not.toBeInTheDocument();
  });
});

describe("ComponentSidebar — 25.2/25.3, search", () => {
  it("filters across name and description", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: FIXTURE,
      isLoading: false,
      error: undefined,
    });
    render(<ComponentSidebar />);

    fireEvent.change(screen.getByLabelText("Search components"), {
      target: { value: "message" },
    });

    expect(screen.getByTestId("sidebar-item-ChatInput")).toBeInTheDocument();
    expect(
      screen.queryByTestId("sidebar-item-ChatOutput")
    ).not.toBeInTheDocument();
  });
});

describe("ComponentSidebar — 25.5, drag payload", () => {
  it("sets the component type on the drag payload", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: FIXTURE,
      isLoading: false,
      error: undefined,
    });
    render(<ComponentSidebar />);

    const item = screen.getByTestId("sidebar-item-ChatInput");
    const dataTransfer = {
      setData: jest.fn(),
      effectAllowed: "",
    };

    fireEvent.dragStart(item, { dataTransfer });

    expect(dataTransfer.setData).toHaveBeenCalledWith(
      "application/x-flow-component-type",
      "ChatInput"
    );
  });
});

describe("ComponentSidebar — 25.6, collapse/expand", () => {
  it("collapses and expands a category on click", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: FIXTURE,
      isLoading: false,
      error: undefined,
    });
    render(<ComponentSidebar />);

    expect(screen.getByTestId("sidebar-item-ChatInput")).toBeVisible();

    fireEvent.click(screen.getByTestId("sidebar-category-core"));

    // Radix Collapsible unmounts/hides content when closed.
    expect(
      screen.queryByTestId("sidebar-item-ChatInput")
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("sidebar-category-core"));

    expect(screen.getByTestId("sidebar-item-ChatInput")).toBeInTheDocument();
  });
});

describe("ComponentSidebar — 25.7, recents", () => {
  it("surfaces a used component under Recently used and persists it", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: FIXTURE,
      isLoading: false,
      error: undefined,
    });
    const { unmount } = render(<ComponentSidebar />);

    fireEvent.dragStart(screen.getByTestId("sidebar-item-ZeroShotAgent"), {
      dataTransfer: { setData: jest.fn(), effectAllowed: "" },
    });

    expect(screen.getByText("Recently used")).toBeInTheDocument();
    unmount();

    // Persisted across remounts (localStorage). ZeroShotAgent now renders
    // twice — once under "Recently used", once under its own category —
    // so the presence check is a count, not a single-match query.
    mockUseComponentTemplates.mockReturnValue({
      data: FIXTURE,
      isLoading: false,
      error: undefined,
    });
    render(<ComponentSidebar />);
    expect(screen.getByText("Recently used")).toBeInTheDocument();
    expect(screen.getAllByTestId("sidebar-item-ZeroShotAgent")).toHaveLength(2);
  });
});

describe("ComponentSidebar — 25.9, loading state", () => {
  it("renders a skeleton, not an empty palette, while loading", () => {
    mockUseComponentTemplates.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: undefined,
    });

    render(<ComponentSidebar />);

    expect(screen.getByTestId("sidebar-loading-skeleton")).toBeInTheDocument();
    expect(screen.queryByText("No components found")).not.toBeInTheDocument();
  });
});
