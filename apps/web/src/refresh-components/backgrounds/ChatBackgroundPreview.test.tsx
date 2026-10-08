import React from "react";
import { render, screen } from "@testing-library/react";
import { createFakeCanvasContext2D } from "@tests/setup/mocks/canvasContext2d";
import { getBackgroundById } from "@/lib/constants/chatBackgrounds";
import { ChatBackgroundPreview } from "./ChatBackgroundPreview";

function requireOption(id: string) {
  const option = getBackgroundById(id);
  if (!option) throw new Error(`missing background option ${id}`);
  return option;
}

describe("ChatBackgroundPreview", () => {
  beforeEach(() => {
    jest
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockImplementation(
        () => createFakeCanvasContext2D() as unknown as RenderingContext
      );
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("shows the supplied placeholder for the none option", () => {
    render(
      <ChatBackgroundPreview
        option={requireOption("none")}
        canvasMode="light"
        noneContent={<span>Nothing</span>}
      />
    );

    expect(screen.getByText("Nothing")).toBeInTheDocument();
  });

  it("paints a photo option's thumbnail as a background image", () => {
    const { container } = render(
      <ChatBackgroundPreview
        option={requireOption("night")}
        canvasMode="light"
        noneContent={null}
      />
    );

    expect(container.querySelector("canvas")).toBeNull();
    expect(
      container.querySelector<HTMLElement>("[style*='background-image']")?.style
        .backgroundImage
    ).toContain("/chat-backgrounds/thumbnails/night.jpg");
  });

  it("renders a canvas option as a static scene instead of an image", () => {
    const { container } = render(
      <ChatBackgroundPreview
        option={requireOption("turksat-uydu")}
        canvasMode="dark"
        noneContent={null}
      />
    );

    expect(container.querySelector("canvas")).not.toBeNull();
    expect(container.querySelector("[style*='background-image']")).toBeNull();
  });
});
