import React from "react";
import { render, cleanup } from "@testing-library/react";
import { createFakeCanvasContext2D } from "@tests/setup/mocks/canvasContext2d";
import { Painter } from "@/lib/turksatBackgrounds/painter";
import { TurksatBackgroundCanvas } from "./TurksatBackgroundCanvas";

/** A controllable observer fake that exposes its constructor's callback so a
 * test can fire it manually — the global stub in `tests/setup/jest.setup.ts`
 * never calls back, which is right for most tests but not for exercising
 * this component's own resize/visibility handling. Resize and intersection
 * get their own subclass (with their own instance list) since a real
 * component mounts one of each and a test needs to address them separately. */
class ControllableObserver {
  callback: (entries: unknown[]) => void;
  observed: Element[] = [];
  constructor(callback: (entries: unknown[]) => void) {
    this.callback = callback;
  }
  observe(el: Element) {
    this.observed.push(el);
  }
  unobserve() {}
  disconnect = jest.fn();
  fire(entries: unknown[]) {
    this.callback(entries);
  }
}

class FakeResizeObserver extends ControllableObserver {
  static instances: FakeResizeObserver[] = [];
  constructor(callback: (entries: unknown[]) => void) {
    super(callback);
    FakeResizeObserver.instances.push(this);
  }
}

class FakeIntersectionObserver extends ControllableObserver {
  static instances: FakeIntersectionObserver[] = [];
  constructor(callback: (entries: unknown[]) => void) {
    super(callback);
    FakeIntersectionObserver.instances.push(this);
  }
}

function stubCanvasContexts(usable = true) {
  jest
    .spyOn(HTMLCanvasElement.prototype, "getContext")
    .mockImplementation((id: string) => {
      if (id !== "2d" || !usable) return null;
      return createFakeCanvasContext2D();
    });
}

function stubBoundingRect(width: number, height: number) {
  jest.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    width,
    height,
    top: 0,
    left: 0,
    right: width,
    bottom: height,
    x: 0,
    y: 0,
    toJSON() {},
  });
}

function stubMatchMedia(reduceMotion: boolean) {
  const listeners = new Set<() => void>();
  window.matchMedia = jest.fn().mockImplementation((query: string) => ({
    matches: query.includes("prefers-reduced-motion") ? reduceMotion : false,
    media: query,
    addEventListener: (_: string, cb: () => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: () => void) => listeners.delete(cb),
    dispatchEvent: jest.fn(),
  }));
}

/** Replaces real rAF with a manually-steppable queue. */
function stubAnimationFrame() {
  let nextId = 1;
  const queue = new Map<number, FrameRequestCallback>();
  window.requestAnimationFrame = jest.fn((cb: FrameRequestCallback) => {
    const id = nextId++;
    queue.set(id, cb);
    return id;
  });
  window.cancelAnimationFrame = jest.fn((id: number) => {
    queue.delete(id);
  });
  return {
    pendingCount: () => queue.size,
    step: (time = 16) => {
      const entries = Array.from(queue.entries());
      queue.clear();
      entries.forEach(([, cb]) => cb(time));
    },
  };
}

describe("TurksatBackgroundCanvas", () => {
  const realResizeObserver = global.ResizeObserver;
  const realIntersectionObserver = global.IntersectionObserver;

  beforeEach(() => {
    FakeResizeObserver.instances = [];
    FakeIntersectionObserver.instances = [];
    // @ts-expect-error — test double, not a spec-complete ResizeObserver.
    global.ResizeObserver = FakeResizeObserver;
    // @ts-expect-error — test double, not a spec-complete IntersectionObserver.
    global.IntersectionObserver = FakeIntersectionObserver;
    stubBoundingRect(800, 600);
  });

  afterEach(() => {
    cleanup();
    jest.restoreAllMocks();
    global.ResizeObserver = realResizeObserver;
    global.IntersectionObserver = realIntersectionObserver;
  });

  it("renders a canvas element", () => {
    stubCanvasContexts();
    stubMatchMedia(false);
    stubAnimationFrame();
    const { container } = render(
      <TurksatBackgroundCanvas company="uydu" mode="dark" />
    );
    expect(container.querySelector("canvas")).not.toBeNull();
  });

  it("starts an animation loop by default", () => {
    stubCanvasContexts();
    stubMatchMedia(false);
    const raf = stubAnimationFrame();
    render(<TurksatBackgroundCanvas company="bilisim" mode="light" />);
    expect(raf.pendingCount()).toBeGreaterThan(0);
  });

  it("does not animate under prefers-reduced-motion", () => {
    stubCanvasContexts();
    stubMatchMedia(true);
    const raf = stubAnimationFrame();
    render(<TurksatBackgroundCanvas company="kablo" mode="dark" />);
    expect(raf.pendingCount()).toBe(0);
  });

  it("does not animate when animate=false (thumbnail mode)", () => {
    stubCanvasContexts();
    stubMatchMedia(false);
    const raf = stubAnimationFrame();
    render(
      <TurksatBackgroundCanvas company="uydu" mode="light" animate={false} />
    );
    expect(raf.pendingCount()).toBe(0);
  });

  it("stops animating once the tab is hidden, and resumes when visible again", () => {
    stubCanvasContexts();
    stubMatchMedia(false);
    const raf = stubAnimationFrame();
    render(<TurksatBackgroundCanvas company="bilisim" mode="dark" />);
    expect(raf.pendingCount()).toBeGreaterThan(0);

    Object.defineProperty(document, "hidden", {
      value: true,
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
    raf.step();
    expect(raf.pendingCount()).toBe(0);

    Object.defineProperty(document, "hidden", {
      value: false,
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(raf.pendingCount()).toBeGreaterThan(0);
  });

  it("stops animating when scrolled off-screen via IntersectionObserver", () => {
    stubCanvasContexts();
    stubMatchMedia(false);
    const raf = stubAnimationFrame();
    render(<TurksatBackgroundCanvas company="kablo" mode="light" />);

    const intersectionObserver = FakeIntersectionObserver.instances.find(
      (o) => o.observed.length > 0
    );
    intersectionObserver!.fire([{ isIntersecting: false }]);
    raf.step();
    expect(raf.pendingCount()).toBe(0);

    intersectionObserver!.fire([{ isIntersecting: true }]);
    expect(raf.pendingCount()).toBeGreaterThan(0);
  });

  it("cancels the animation frame and disconnects observers on unmount", () => {
    stubCanvasContexts();
    stubMatchMedia(false);
    const raf = stubAnimationFrame();
    const { unmount } = render(
      <TurksatBackgroundCanvas company="uydu" mode="dark" />
    );
    expect(raf.pendingCount()).toBeGreaterThan(0);

    unmount();

    expect(window.cancelAnimationFrame).toHaveBeenCalled();
    [
      ...FakeResizeObserver.instances,
      ...FakeIntersectionObserver.instances,
    ].forEach((o) => expect(o.disconnect).toHaveBeenCalled());
  });

  it("rebuilds on resize", () => {
    stubCanvasContexts();
    stubMatchMedia(false);
    stubAnimationFrame();
    render(
      <TurksatBackgroundCanvas company="bilisim" mode="light" animate={false} />
    );

    const resizeObserver = FakeResizeObserver.instances.find(
      (o) => o.observed.length > 0
    );
    expect(() => resizeObserver!.fire([])).not.toThrow();
  });

  it("does not throw when no 2D context is available", () => {
    stubCanvasContexts(false);
    stubMatchMedia(false);
    stubAnimationFrame();
    expect(() =>
      render(<TurksatBackgroundCanvas company="uydu" mode="dark" />)
    ).not.toThrow();
  });

  it("stops animating instead of crashing the page when a frame throws", () => {
    stubCanvasContexts();
    stubMatchMedia(false);
    const raf = stubAnimationFrame();
    const consoleError = jest.spyOn(console, "error").mockImplementation();
    jest.spyOn(Painter.prototype, "tick").mockImplementation(() => {
      throw new Error("bad frame");
    });
    render(<TurksatBackgroundCanvas company="kablo" mode="dark" />);

    expect(() => raf.step()).not.toThrow();

    expect(raf.pendingCount()).toBe(0);
    expect(consoleError).toHaveBeenCalledTimes(1);
  });

  it("pauses when the browser drops the canvas context, and rebuilds when it is restored", () => {
    stubCanvasContexts();
    stubMatchMedia(false);
    const raf = stubAnimationFrame();
    const { container } = render(
      <TurksatBackgroundCanvas company="uydu" mode="light" />
    );
    const canvas = container.querySelector("canvas")!;
    const build = jest.spyOn(Painter.prototype, "build");

    // A lost context is only restorable if the page cancels the default.
    const lost = new Event("contextlost", { cancelable: true });
    canvas.dispatchEvent(lost);
    raf.step();

    expect(lost.defaultPrevented).toBe(true);
    expect(raf.pendingCount()).toBe(0);

    canvas.dispatchEvent(new Event("contextrestored"));

    expect(build).toHaveBeenCalledTimes(1);
    expect(raf.pendingCount()).toBeGreaterThan(0);
  });

  it("scales a stale bitmap uniformly while a resize rebuild is pending, instead of stretching it", () => {
    stubCanvasContexts();
    stubMatchMedia(false);
    stubAnimationFrame();
    const { container } = render(
      <TurksatBackgroundCanvas company="kablo" mode="dark" animate={false} />
    );

    expect(container.querySelector("canvas")).toHaveClass("object-cover");
  });

  it("builds the scene around the message column's real on-screen width", () => {
    stubCanvasContexts();
    stubMatchMedia(false);
    stubAnimationFrame();
    jest
      .spyOn(HTMLElement.prototype, "offsetWidth", "get")
      .mockReturnValue(700);
    const build = jest.spyOn(Painter.prototype, "build");

    render(
      <TurksatBackgroundCanvas company="uydu" mode="dark" animate={false} />
    );

    expect(build).toHaveBeenCalledWith("uydu", true, 800, 600, 700);
  });
});
