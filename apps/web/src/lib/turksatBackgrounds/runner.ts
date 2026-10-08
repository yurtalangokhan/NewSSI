import { measureColumnCssPx } from "./column";
import { Painter } from "./painter";
import type { TurksatCompany } from "./types";

const RESIZE_DEBOUNCE_MS = 120;

export interface BackgroundRunnerOptions {
  company: TurksatCompany;
  dark: boolean;
  /** `false` paints one static frame and never starts a loop. */
  animate: boolean;
}

/**
 * Owns the lifecycle of one TÜRKSAT scene drawing into a canvas: building it
 * at the canvas's real size, rebuilding on resize and canvas-context
 * restoration, and driving the rAF loop only while it is worth running (tab
 * visible, canvas on-screen, no `prefers-reduced-motion`, context alive).
 *
 * A background is decoration, so a scene that throws must never take the page
 * down: the failure is reported once and the loop stops, leaving the last
 * painted frame in place.
 */
export class BackgroundRunner {
  private readonly painter: Painter;
  private resizeObserver: ResizeObserver | undefined;
  private intersectionObserver: IntersectionObserver | undefined;
  private reduceMotion: MediaQueryList | undefined;
  private resizeTimer: ReturnType<typeof setTimeout> | undefined;
  private raf = 0;
  private running = false;
  private lastTimestamp = 0;
  private isVisible = true;
  private contextLost = false;
  private failed = false;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly options: BackgroundRunnerOptions
  ) {
    this.painter = new Painter(canvas);
  }

  start(): void {
    if (!this.painter.isUsable) return;

    this.rebuild();

    if (typeof ResizeObserver !== "undefined") {
      this.resizeObserver = new ResizeObserver(this.scheduleRebuild);
      this.resizeObserver.observe(this.canvas);
    }
    this.canvas.addEventListener("contextlost", this.onContextLost);
    this.canvas.addEventListener("contextrestored", this.onContextRestored);

    if (!this.options.animate) return;

    this.reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    this.reduceMotion.addEventListener("change", this.syncRunning);
    document.addEventListener("visibilitychange", this.syncRunning);
    if (typeof IntersectionObserver !== "undefined") {
      this.intersectionObserver = new IntersectionObserver(
        (entries) => {
          this.isVisible = entries[0]?.isIntersecting ?? true;
          this.syncRunning();
        },
        { threshold: 0 }
      );
      this.intersectionObserver.observe(this.canvas);
    }
    this.syncRunning();
  }

  dispose(): void {
    this.stopLoop();
    clearTimeout(this.resizeTimer);
    this.resizeObserver?.disconnect();
    this.intersectionObserver?.disconnect();
    this.reduceMotion?.removeEventListener("change", this.syncRunning);
    document.removeEventListener("visibilitychange", this.syncRunning);
    this.canvas.removeEventListener("contextlost", this.onContextLost);
    this.canvas.removeEventListener("contextrestored", this.onContextRestored);
  }

  private readonly rebuild = (): void => {
    const rect = this.canvas.getBoundingClientRect();
    this.guarded(() => {
      this.painter.build(
        this.options.company,
        this.options.dark,
        rect.width,
        rect.height,
        measureColumnCssPx(this.canvas)
      );
      this.painter.draw();
    });
  };

  private readonly scheduleRebuild = (): void => {
    clearTimeout(this.resizeTimer);
    this.resizeTimer = setTimeout(this.rebuild, RESIZE_DEBOUNCE_MS);
  };

  /** Called with `preventDefault` so the browser is allowed to restore the
   * context later (it will not otherwise). */
  private readonly onContextLost = (event: Event): void => {
    event.preventDefault();
    this.contextLost = true;
    this.syncRunning();
  };

  private readonly onContextRestored = (): void => {
    this.contextLost = false;
    this.rebuild();
    this.syncRunning();
  };

  private get shouldRun(): boolean {
    return (
      this.options.animate &&
      this.isVisible &&
      !document.hidden &&
      !this.reduceMotion?.matches &&
      !this.contextLost &&
      !this.failed
    );
  }

  private readonly syncRunning = (): void => {
    if (this.shouldRun && !this.running) {
      this.running = true;
      this.lastTimestamp = 0;
      this.raf = requestAnimationFrame(this.frame);
    } else if (!this.shouldRun && this.running) {
      this.stopLoop();
      if (!this.contextLost && !this.failed) this.painter.draw();
    }
  };

  private readonly frame = (now: number): void => {
    // `Painter.tick` clamps the step, so a long gap after the tab was hidden
    // is safe to pass through as-is.
    const dtSeconds = this.lastTimestamp
      ? (now - this.lastTimestamp) / 1000
      : 1 / 60;
    this.lastTimestamp = now;
    if (this.guarded(() => this.painter.tick(dtSeconds))) {
      this.raf = requestAnimationFrame(this.frame);
    } else {
      this.running = false;
    }
  };

  private stopLoop(): void {
    if (this.running) cancelAnimationFrame(this.raf);
    this.running = false;
  }

  /** Runs `work`; a throw is reported once, halts animation, and returns
   * `false` so the caller can stop scheduling frames. */
  private guarded(work: () => void): boolean {
    try {
      work();
      return true;
    } catch (error) {
      if (!this.failed) {
        console.error("TÜRKSAT background stopped after an error", error);
      }
      this.failed = true;
      return false;
    }
  }
}
