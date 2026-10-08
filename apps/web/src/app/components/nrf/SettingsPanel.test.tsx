import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SettingsPanel } from "./SettingsPanel";

// The panel's header buttons (theme toggle, close) render a tooltip, which
// requires a TooltipProvider ancestor.
function renderPanel(props: React.ComponentProps<typeof SettingsPanel>) {
  return render(
    <TooltipProvider>
      <SettingsPanel {...props} />
    </TooltipProvider>
  );
}

const mockUpdateUserChatBackground = jest.fn();
const mockUser: { preferences: { chat_background: string | null } } = {
  preferences: { chat_background: null },
};

jest.mock("@/providers/UserProvider", () => ({
  useUser: () => ({
    user: mockUser,
    updateUserChatBackground: mockUpdateUserChatBackground,
  }),
}));

jest.mock("@/components/context/NRFPreferencesContext", () => ({
  useNRFPreferences: () => ({ useAtlasAsNewTab: false }),
}));

let mockResolvedTheme = "light";
jest.mock("next-themes", () => ({
  useTheme: () => ({
    theme: mockResolvedTheme,
    resolvedTheme: mockResolvedTheme,
    setTheme: jest.fn(),
  }),
}));

// The canvas component's own rendering/lifecycle is covered by its own test
// suite; here we only need to know *which* thumbnail flavor SettingsPanel
// chose to render for a given option.
jest.mock("@/refresh-components/backgrounds/TurksatBackgroundCanvas", () => ({
  TurksatBackgroundCanvas: ({
    company,
    mode,
  }: {
    company: string;
    mode: string;
  }) => (
    <div
      data-testid="turksat-canvas-thumbnail"
      data-scene={`${company}-${mode}`}
    />
  ),
}));

describe("SettingsPanel background picker", () => {
  beforeEach(() => {
    mockUpdateUserChatBackground.mockClear();
    mockUser.preferences.chat_background = null;
    mockResolvedTheme = "light";
  });

  const noop = () => {};

  it.each(["light", "dark"])(
    "renders one %s-mode canvas preview per TÜRKSAT company",
    (mode) => {
      mockResolvedTheme = mode;
      renderPanel({
        settingsOpen: true,
        toggleSettings: noop,
        handleUseAtlasToggle: noop,
      });

      const scenes = screen
        .getAllByTestId("turksat-canvas-thumbnail")
        .map((el) => el.getAttribute("data-scene"));

      expect(scenes.sort()).toEqual(
        ["bilisim", "kablo", "uydu"].map((company) => `${company}-${mode}`)
      );
    }
  );

  it("renders a plain background-image thumbnail for a photo option", () => {
    renderPanel({
      settingsOpen: true,
      toggleSettings: noop,
      handleUseAtlasToggle: noop,
    });

    const mountainsThumb = screen.getByRole("button", { name: /Mountains/i });
    expect(
      mountainsThumb.querySelector('[data-testid="turksat-canvas-thumbnail"]')
    ).toBeNull();
    expect(mountainsThumb.querySelector("div[style]")).toHaveStyle(
      "background-image: url(/chat-backgrounds/thumbnails/mountains.jpg)"
    );
  });

  it("selects a TÜRKSAT background by id when its thumbnail is clicked", async () => {
    const user = userEvent.setup();
    renderPanel({
      settingsOpen: true,
      toggleSettings: noop,
      handleUseAtlasToggle: noop,
    });

    await user.click(screen.getByRole("button", { name: /Türksat Uydu/i }));

    expect(mockUpdateUserChatBackground).toHaveBeenCalledWith("turksat-uydu");
  });

  it("marks the active TÜRKSAT background as selected", () => {
    mockUser.preferences.chat_background = "turksat-kablo";
    renderPanel({
      settingsOpen: true,
      toggleSettings: noop,
      handleUseAtlasToggle: noop,
    });

    const selected = screen.getByRole("button", {
      name: /Türksat Kablo background \(selected\)/i,
    });
    expect(selected).toBeInTheDocument();
  });

  it("names background tiles with the app tooltip instead of a native title", async () => {
    const user = userEvent.setup();
    renderPanel({
      settingsOpen: true,
      toggleSettings: noop,
      handleUseAtlasToggle: noop,
    });
    const tile = screen.getByRole("button", { name: /Türksat Uydu/i });

    expect(tile).not.toHaveAttribute("title");

    await user.hover(tile);

    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "Türksat Uydu"
    );
  });
});
