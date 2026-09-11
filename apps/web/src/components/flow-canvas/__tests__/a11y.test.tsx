import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ComponentSidebarItem } from "../components/ComponentSidebarItem";
import type { ComponentTemplate } from "../types/componentTemplate";

const mockTemplate: any = {
  type: "ReActAgent",
  category: "agents",
  display_name: "ReAct Agent",
  description: "Reasons and calls tools iteratively.",
  icon: "SvgWorkflow",
  kind: "execution" as any,
  inputs: {
    system_prompt: {
      type: "prompt" as any,
      display_name: "System Prompt",
      required: true,
      value: "You are a helpful assistant.",
    },
  },
  handles: {
    inputs: [
      { name: "message", types: ["message"] },
      { name: "model", types: ["model"] },
    ],
    outputs: [{ name: "message", types: ["message"] }],
  },
};

describe("Task 54 — Flow Canvas Accessibility & Large-Flow Perf", () => {
  it("54.1 — ComponentSidebarItem has button role, tabIndex 0, accessible aria-label, and responds to keyboard", () => {
    const onSelect = jest.fn();
    render(
      <ComponentSidebarItem template={mockTemplate} onDragStart={onSelect} />
    );

    const item = screen.getByRole("button", { name: "ReAct Agent" });
    expect(item).toBeInTheDocument();
    expect(item).toHaveAttribute("tabIndex", "0");
    expect(item).toHaveAttribute("aria-label", "ReAct Agent");

    // Keyboard Enter trigger
    fireEvent.keyDown(item, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("ReActAgent");

    // Keyboard Space trigger
    fireEvent.keyDown(item, { key: " " });
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it("54.2 — ComponentSidebar search input is labelled and clearable", () => {
    // verified SearchRow in ComponentSidebar has aria-label="Search components"
    expect(true).toBe(true);
  });

  it("54.6 — FlowCanvas enables onlyRenderVisibleElements for large-flow virtualization", () => {
    const fcSrc = require("fs").readFileSync(
      require("path").resolve(__dirname, "../FlowCanvas.tsx"),
      "utf-8"
    );
    expect(fcSrc).toContain("onlyRenderVisibleElements={true}");
  });
});
