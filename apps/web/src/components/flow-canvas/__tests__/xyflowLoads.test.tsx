/**
 * Task 20.1 — prove @xyflow/react actually mounts under jest + jsdom.
 *
 * xyflow ships ESM and imports its own CSS. Both are exactly the kind of
 * thing this repo's jest config has to be told about (see
 * transformIgnorePatterns / moduleNameMapper). Finding that here, in a
 * three-line render, is far cheaper than finding it inside Task 24's
 * 800-line canvas port.
 *
 * Brief: .tmp/flow-canvas-task-20-brief.md
 */

import { render, screen } from "@testing-library/react";
import { ReactFlow, ReactFlowProvider } from "@xyflow/react";
import React from "react";

describe("@xyflow/react under jest/jsdom", () => {
  it("20.1 — mounts an empty canvas without ESM or CSS errors", () => {
    render(
      <div style={{ width: 800, height: 600 }} data-testid="canvas-host">
        <ReactFlowProvider>
          <ReactFlow nodes={[]} edges={[]} />
        </ReactFlowProvider>
      </div>
    );

    expect(screen.getByTestId("canvas-host")).toBeInTheDocument();
  });

  it("20.1 — renders a provided node", () => {
    render(
      <div style={{ width: 800, height: 600 }}>
        <ReactFlowProvider>
          <ReactFlow
            nodes={[
              {
                id: "n1",
                position: { x: 0, y: 0 },
                data: { label: "hello-canvas" },
              },
            ]}
            edges={[]}
          />
        </ReactFlowProvider>
      </div>
    );

    expect(screen.getByText("hello-canvas")).toBeInTheDocument();
  });
});
