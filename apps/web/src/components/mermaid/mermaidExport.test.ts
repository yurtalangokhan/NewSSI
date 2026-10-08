/**
 * @jest-environment jsdom
 *
 * This file is matched by the "unit" (node) Jest project via
 * src/components/mermaid/**\/*.test.ts, but downloadBlob/svgToPngBlob need
 * DOM globals (URL.createObjectURL, canvas, Image, anchor). The docblock
 * above overrides the project's environment for this file only.
 */
import {
  downloadBlob,
  mermaidFileName,
  svgToPngBlob,
} from "@/components/mermaid/mermaidExport";

describe("mermaidFileName", () => {
  it("names downloads after the diagram kind", () => {
    expect(mermaidFileName("sequence", "svg")).toBe("diagram-sequence.svg");
    expect(mermaidFileName(null, "png")).toBe("diagram.png");
  });
});

const SVG =
  '<svg id="mmd1z" width="100%" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200"></svg>';

describe("downloadBlob", () => {
  let createObjectURL: jest.Mock;
  let revokeObjectURL: jest.Mock;

  beforeEach(() => {
    jest.useFakeTimers();
    createObjectURL = jest.fn().mockReturnValue("blob:mock-url");
    revokeObjectURL = jest.fn();
    // jsdom does not implement URL.createObjectURL/revokeObjectURL.
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it("creates an object URL, triggers a click, and revokes it after the delay", () => {
    const clickSpy = jest
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    downloadBlob(new Blob(["data"]), "diagram.svg");

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).not.toHaveBeenCalled();

    jest.advanceTimersByTime(10000);

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
    clickSpy.mockRestore();
  });
});

describe("svgToPngBlob", () => {
  let createObjectURL: jest.Mock;
  let revokeObjectURL: jest.Mock;
  let toBlobImpl: (this: HTMLCanvasElement, callback: BlobCallback) => void;
  let imageOutcome: "load" | "error";

  beforeEach(() => {
    createObjectURL = jest.fn().mockReturnValue("blob:mock-url");
    revokeObjectURL = jest.fn();
    // jsdom does not implement URL.createObjectURL/revokeObjectURL.
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;

    imageOutcome = "load";
    Object.defineProperty(global.Image.prototype, "src", {
      configurable: true,
      set() {
        setTimeout(() => {
          if (imageOutcome === "load") this.onload?.(new Event("load"));
          else this.onerror?.(new Event("error"));
        }, 0);
      },
    });

    toBlobImpl = function (callback: BlobCallback) {
      callback(new Blob(["png-bytes"], { type: "image/png" }));
    };
    jest.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      fillStyle: "",
      fillRect: jest.fn(),
      drawImage: jest.fn(),
    } as unknown as CanvasRenderingContext2D);
    jest
      .spyOn(HTMLCanvasElement.prototype, "toBlob")
      .mockImplementation(function (
        this: HTMLCanvasElement,
        callback: BlobCallback
      ) {
        toBlobImpl.call(this, callback);
      });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("resolves a PNG blob, sizes the canvas within pngScale's cap, and revokes the object URL", async () => {
    const blob = await svgToPngBlob(SVG, "#ffffff");

    expect(blob.type).toBe("image/png");
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });

  it("revokes the object URL even when toBlob yields null", async () => {
    toBlobImpl = function (callback: BlobCallback) {
      callback(null);
    };

    await expect(svgToPngBlob(SVG, "#ffffff")).rejects.toThrow(
      "PNG encoding failed"
    );
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });

  it("revokes the object URL when the image fails to decode", async () => {
    imageOutcome = "error";

    await expect(svgToPngBlob(SVG, "#ffffff")).rejects.toThrow(
      "SVG could not be decoded"
    );
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
  });
});
