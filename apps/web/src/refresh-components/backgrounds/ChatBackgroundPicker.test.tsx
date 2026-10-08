import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createFakeCanvasContext2D } from "@tests/setup/mocks/canvasContext2d";
import { getBackgroundById } from "@/lib/constants/chatBackgrounds";
import { preloadChatBackgroundImage } from "@/lib/chatBackgroundClient";
import { ChatBackgroundPicker } from "./ChatBackgroundPicker";

jest.mock("@/lib/chatBackgroundClient", () => ({
  preloadChatBackgroundImage: jest.fn(),
}));

jest.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: "light" }),
}));

function renderPicker(selectedId = "none", onSelect = jest.fn()) {
  render(
    <ChatBackgroundPicker
      selectedId={selectedId}
      noneLabel="None"
      onSelect={onSelect}
    />
  );
  return onSelect;
}

describe("ChatBackgroundPicker", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockImplementation(
        () => createFakeCanvasContext2D() as unknown as RenderingContext
      );
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("offers every background as a labelled button", () => {
    renderPicker();

    expect(
      screen.getByRole("button", { name: "Türksat Uydu background" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Night background" })
    ).toBeInTheDocument();
  });

  it("marks only the selected background", () => {
    renderPicker("night");

    expect(
      screen.getByRole("button", { name: "Night background (selected)" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Clouds background" })
    ).toBeInTheDocument();
  });

  it("reports the chosen option", async () => {
    const onSelect = renderPicker();

    await userEvent.click(
      screen.getByRole("button", { name: "Türksat Kablo background" })
    );

    expect(onSelect).toHaveBeenCalledWith(getBackgroundById("turksat-kablo"));
  });

  it("names a background with the app tooltip, not the browser's native title", async () => {
    renderPicker();
    const button = screen.getByRole("button", { name: "Night background" });

    expect(button).not.toHaveAttribute("title");

    await userEvent.hover(button);

    expect(await screen.findByRole("tooltip")).toHaveTextContent("Night");
  });

  it("warms the image cache for a photo on hover, but not for a canvas scene or none", async () => {
    renderPicker();

    await userEvent.hover(
      screen.getByRole("button", { name: "Türksat Uydu background" })
    );
    await userEvent.hover(
      screen.getByRole("button", { name: "None background (selected)" })
    );
    expect(preloadChatBackgroundImage).not.toHaveBeenCalled();

    await userEvent.hover(
      screen.getByRole("button", { name: "Night background" })
    );
    expect(preloadChatBackgroundImage).toHaveBeenCalledWith(
      "/chat-backgrounds/night.jpg"
    );
  });
});
