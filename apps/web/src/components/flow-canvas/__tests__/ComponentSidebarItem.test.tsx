import { render, screen } from "@testing-library/react";
import { ComponentSidebarItem } from "../components/ComponentSidebarItem";
import type { ComponentTemplate } from "../types/componentTemplate";

function template(
  overrides: Partial<ComponentTemplate> = {}
): ComponentTemplate {
  return {
    type: "ChatInput",
    category: "io",
    display_name: "Chat Input",
    description: "Reads chat input",
    icon: null,
    template_version: 1,
    lifecycle: "stable",
    kind: "execution",
    fields: [],
    ...overrides,
  } as ComponentTemplate;
}

describe("ComponentSidebarItem", () => {
  it("disables text selection on the draggable row so clicking the label doesn't hijack the drag gesture with a text selection instead", () => {
    render(<ComponentSidebarItem template={template()} />);

    const row = screen.getByTestId("sidebar-item-ChatInput");
    expect(row).toHaveClass("select-none");
  });
});
