import React from "react";
import { render, screen } from "@testing-library/react";
import McpToolsPopover from "./McpToolsPopover";
import type { MinimalPersonaSnapshot } from "@/lib/api/domains/agents/types";

jest.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: jest.fn() },
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) =>
      options?.count === undefined ? key : `${key}|${options.count}`,
  }),
}));

jest.mock("@opal/icons", () => {
  const Icon = () => <span />;
  return new Proxy({}, { get: () => Icon });
});

jest.mock("@opal/components", () => ({
  Button: ({ children }: { children?: React.ReactNode }) => (
    <button type="button">{children}</button>
  ),
  Tag: ({ title }: { title: string }) => <div data-testid="tag">{title}</div>,
}));

jest.mock("@/refresh-components/Popover", () => {
  function MockPopover({ children }: { children: React.ReactNode }) {
    return <div>{children}</div>;
  }
  MockPopover.Trigger = ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  );
  MockPopover.Content = ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  );
  MockPopover.Menu = ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  );
  return { __esModule: true, default: MockPopover };
});

function agent(
  tools: MinimalPersonaSnapshot["tools"],
  extra: Record<string, unknown> = {}
): MinimalPersonaSnapshot {
  return {
    id: 37,
    name: "Knowledge Agent",
    base_agent: "configurable-mcp-agent",
    tools,
    ...extra,
  } as unknown as MinimalPersonaSnapshot;
}

const tool = (id: number, name: string, display_name: string) =>
  ({
    id,
    name,
    display_name,
    description: "",
  }) as MinimalPersonaSnapshot["tools"][number];

describe("McpToolsPopover", () => {
  it("lists assigned RAG and GraphRAG collections as knowledge sources", () => {
    render(
      <McpToolsPopover
        selectedAgent={agent([
          tool(1, "database_search", "Quantum Physics"),
          tool(2, "graph_search", "Org Chart"),
        ])}
      />
    );

    expect(
      screen.getByText("inputBar.knowledgeSourcesButton (2)")
    ).toBeInTheDocument();
    expect(
      screen.getByText("inputBar.knowledgeSourcesTitle")
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/inputBar.mcpToolsButton/)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("inputBar.mcpToolsTitle")
    ).not.toBeInTheDocument();
    expect(screen.getByText("Quantum Physics")).toBeInTheDocument();
    expect(screen.getByText("RAG")).toBeInTheDocument();
    expect(screen.getByText("Org Chart")).toBeInTheDocument();
    expect(screen.getByText("GraphRAG")).toBeInTheDocument();
  });

  it("keeps real MCP tools in their own section next to knowledge sources", () => {
    render(
      <McpToolsPopover
        selectedAgent={agent([
          tool(1, "database_search", "Quantum Physics"),
          tool(2, "web_search", "Web Search"),
        ])}
      />
    );

    expect(
      screen.getByText("inputBar.knowledgeSourcesButton (1)")
    ).toBeInTheDocument();
    expect(screen.getByText("inputBar.otherToolsSection")).toBeInTheDocument();
    expect(screen.getByText("Web Search")).toBeInTheDocument();
  });

  it("stays an MCP tools list when the agent has no knowledge sources", () => {
    render(
      <McpToolsPopover
        selectedAgent={agent([tool(1, "web_search", "Web Search")])}
      />
    );

    expect(screen.getByText("inputBar.mcpToolsButton (1)")).toBeInTheDocument();
    expect(
      screen.queryByText(/inputBar.knowledgeSources/)
    ).not.toBeInTheDocument();
  });

  it("passes the source count to i18n so the plural is locale-owned", () => {
    render(
      <McpToolsPopover
        selectedAgent={agent([
          tool(1, "database_search", "Quantum Physics"),
          tool(2, "graph_search", "Org Chart"),
        ])}
      />
    );

    expect(
      screen.getByText("inputBar.knowledgeSourcesCount|2")
    ).toBeInTheDocument();
  });

  it("passes the tool count to i18n for plain tool lists", () => {
    render(
      <McpToolsPopover
        selectedAgent={agent([tool(1, "web_search", "Web Search")])}
      />
    );

    expect(screen.getByText("inputBar.toolsCount|1")).toBeInTheDocument();
  });

  it("falls back to title-cased mcp_tools names when there are no snapshots", () => {
    render(
      <McpToolsPopover
        selectedAgent={agent([], { mcp_tools: ["fetch_web_page"] })}
      />
    );

    expect(screen.getByText("Fetch Web Page")).toBeInTheDocument();
    expect(screen.getByText("inputBar.mcpToolsButton (1)")).toBeInTheDocument();
  });

  it("shows the empty state when the agent has no tools at all", () => {
    render(<McpToolsPopover selectedAgent={agent([])} />);

    expect(screen.getByText("inputBar.noMcpTools")).toBeInTheDocument();
    expect(screen.getByText("inputBar.noMcpToolsHint")).toBeInTheDocument();
    expect(screen.getByText("inputBar.mcpToolsButton (0)")).toBeInTheDocument();
  });

  it("renders two collections that share a retrieval tool name", () => {
    render(
      <McpToolsPopover
        selectedAgent={agent([
          tool(1, "database_search", "Physics"),
          tool(2, "database_search", "Chemistry"),
        ])}
      />
    );

    expect(screen.getByText("Physics")).toBeInTheDocument();
    expect(screen.getByText("Chemistry")).toBeInTheDocument();
  });

  it("uses only real token classes (no opacity modifiers, no invented tokens)", () => {
    const { container } = render(
      <McpToolsPopover
        selectedAgent={agent([
          tool(1, "database_search", "Quantum Physics"),
          tool(2, "web_search", "Web Search"),
        ])}
      />
    );

    const classes = Array.from(container.querySelectorAll("[class]"))
      .map((el) => el.getAttribute("class"))
      .join(" ");
    expect(classes).not.toMatch(/(bg|divide|border|text)-[a-z0-9-]+\/\d+/);
    expect(classes).not.toContain("border-border-subtle");
    expect(classes).not.toContain("py-0.2");
    expect(classes).not.toMatch(/text-\[\d+px\]/);
  });

  it("renders visible text through the Text primitive rather than raw spans", () => {
    render(
      <McpToolsPopover
        selectedAgent={agent([tool(1, "database_search", "Quantum Physics")])}
      />
    );

    const label = screen.getByText("Quantum Physics");
    expect(label.className).toMatch(/font-/);
  });
});
