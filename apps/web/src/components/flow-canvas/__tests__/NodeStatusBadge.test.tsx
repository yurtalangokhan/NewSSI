import type { ReactElement } from "react";
import { render as rtlRender, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { createI18nInstance } from "@/i18n/config";
import { NodeStatusBadge } from "../components/NodeStatusBadge";

// The badge's token/duration copy goes through `t(key, default, { count })`;
// without an i18n instance the `{{count}}` placeholder is never interpolated.
const i18n = createI18nInstance("en");
const render = (ui: ReactElement) =>
  rtlRender(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);

describe("NodeStatusBadge", () => {
  it("renders null if status is null or undefined", () => {
    const { container } = render(<NodeStatusBadge status={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("45.3 — renders running spinner when status is running", () => {
    render(
      <NodeStatusBadge
        status={{
          status: "running",
          startedAt: Date.now(),
          endedAt: null,
          durationMs: null,
          tokenCount: null,
        }}
      />
    );

    expect(screen.getByTestId("node-status-badge")).toBeInTheDocument();
    expect(screen.getByTestId("status-running-icon")).toBeInTheDocument();
    expect(screen.getByText("Running…")).toBeInTheDocument();
  });

  it("45.4 — renders duration and check icon when status is done", () => {
    render(
      <NodeStatusBadge
        status={{
          status: "done",
          startedAt: 1000,
          endedAt: 2250,
          durationMs: 1250,
          tokenCount: 15,
        }}
      />
    );

    expect(screen.getByTestId("node-status-badge")).toBeInTheDocument();
    expect(screen.getByTestId("status-done-icon")).toBeInTheDocument();
    expect(screen.getByText("1.25s")).toBeInTheDocument();
    expect(screen.getByText("15 tok")).toBeInTheDocument();
  });

  it("45.5 — renders failed icon when status is error", () => {
    render(
      <NodeStatusBadge
        status={{
          status: "error",
          startedAt: 1000,
          endedAt: 1500,
          durationMs: 500,
          tokenCount: null,
        }}
      />
    );

    expect(screen.getByTestId("node-status-badge")).toBeInTheDocument();
    expect(screen.getByTestId("status-error-icon")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});
