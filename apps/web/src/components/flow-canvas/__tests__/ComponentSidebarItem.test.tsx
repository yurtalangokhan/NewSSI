import { fireEvent, render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { createI18nInstance } from "@/i18n/config";
import { ComponentSidebarItem } from "../components/ComponentSidebarItem";
import { createFlowStore } from "../stores/flowStore";
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
    inputs: {},
    handles: { inputs: [], outputs: [] },
    ...overrides,
  };
}

describe("ComponentSidebarItem", () => {
  it("disables text selection on the draggable row so clicking the label doesn't hijack the drag gesture with a text selection instead", () => {
    render(<ComponentSidebarItem template={template()} />);

    const row = screen.getByTestId("sidebar-item-ChatInput");
    expect(row).toHaveClass("select-none");
  });
});

describe("ComponentSidebarItem — palette hover glow preview", () => {
  it("shows an output port dot per declared output while hovered, and none while not", () => {
    const store = createFlowStore();
    render(
      <ComponentSidebarItem
        template={template({
          handles: {
            inputs: [],
            outputs: [{ name: "message", types: ["Model"] }],
          },
        })}
        store={store}
      />
    );

    const row = screen.getByTestId("sidebar-item-ChatInput");
    expect(
      screen.queryByTestId("sidebar-item-ChatInput-port-message")
    ).not.toBeInTheDocument();

    fireEvent.mouseEnter(row);
    expect(
      screen.getByTestId("sidebar-item-ChatInput-port-message")
    ).toBeInTheDocument();

    fireEvent.mouseLeave(row);
    expect(
      screen.queryByTestId("sidebar-item-ChatInput-port-message")
    ).not.toBeInTheDocument();
  });

  it("sets the store's paletteHoverOrigin to the template's output types on hover, and clears it on leave", () => {
    const store = createFlowStore();
    render(
      <ComponentSidebarItem
        template={template({
          handles: {
            inputs: [],
            outputs: [{ name: "message", types: ["Model"] }],
          },
        })}
        store={store}
      />
    );

    const row = screen.getByTestId("sidebar-item-ChatInput");
    fireEvent.mouseEnter(row);
    expect(store.getState().paletteHoverOrigin).toEqual({
      types: ["Model"],
      handleType: "source",
    });

    fireEvent.mouseLeave(row);
    expect(store.getState().paletteHoverOrigin).toBeNull();
  });

  it("renders no port dots and never touches the store for a component with no outputs", () => {
    const store = createFlowStore();
    render(<ComponentSidebarItem template={template()} store={store} />);

    const row = screen.getByTestId("sidebar-item-ChatInput");
    fireEvent.mouseEnter(row);

    expect(store.getState().paletteHoverOrigin).toBeNull();
  });
});

describe("ComponentSidebarItem — lifecycle badge", () => {
  function renderIn(locale: "en" | "tr", lifecycle: "beta" | "deprecated") {
    const i18n = createI18nInstance(locale);
    return render(
      <I18nextProvider i18n={i18n}>
        <ComponentSidebarItem template={template({ lifecycle })} />
      </I18nextProvider>
    );
  }

  it("shows the locale copy of the lifecycle instead of the raw API value", () => {
    renderIn("tr", "deprecated");

    expect(screen.getByText("Kullanımdan Kaldırıldı")).toBeInTheDocument();
    expect(screen.queryByText("deprecated")).not.toBeInTheDocument();
  });

  it("shows the English copy under the English locale", () => {
    renderIn("en", "beta");

    expect(screen.getByText("Beta")).toBeInTheDocument();
  });

  it("shows no badge for stable components", () => {
    render(<ComponentSidebarItem template={template()} />);

    expect(screen.queryByText("Kararlı")).not.toBeInTheDocument();
    expect(screen.queryByText("stable")).not.toBeInTheDocument();
  });
});
