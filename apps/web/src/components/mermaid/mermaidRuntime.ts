/**
 * Browser-only Mermaid runtime.
 *
 * - Mermaid 11.16.0 (the version the server validator bundles) is imported
 *   lazily on the first render, never at module load, so SSR never runs it.
 * - Mermaid keeps global config, so `initialize(theme)` and `render` must run
 *   as one unit. Every job goes through a single promise queue and yields to
 *   the event loop first, so a burst of diagrams cannot starve input.
 * - Results are cached by (theme key, source) in an LRU. Identical in-flight
 *   requests share one promise.
 * - Every job has a deadline, so one job that never settles (a stalled lazy
 *   chunk, a hung layout) cannot hold the queue for every later diagram.
 * - A queued job whose subscribers all aborted is skipped before any work.
 */
import { LruCache } from "@/components/mermaid/lruCache";
import {
  MermaidRenderError,
  toMermaidDiagnostic,
} from "@/components/mermaid/mermaidDiagnostics";
import { MERMAID_MAX_SOURCE_CHARS } from "@/components/mermaid/mermaidSource";
import type { MermaidThemeConfig } from "@/components/mermaid/mermaidTheme";

export const MERMAID_MAX_EDGES = 500;
const CACHE_CAPACITY = 64;
/** Upper bound for one queued job (yield, load, initialize and render). */
export const MERMAID_JOB_TIMEOUT_MS = 10_000;
const TIMEOUT_MESSAGE = "Rendering took too long and was stopped.";

/**
 * Keys that `%%{init}%%` directives and front-matter `config` inside a diagram
 * may not override. It covers Mermaid's defaults plus label mode, theme and
 * the other top-level keys that change security or colors: `themeCSS` (raw CSS
 * injected into the SVG), `dompurifyConfig` (Mermaid's own sanitizer
 * settings), `darkMode`, `look` and `arrowMarkerAbsolute`. Diagram-type
 * sections (`flowchart`, `sequence`, ...) stay overridable on purpose, so a
 * diagram can still tune its own layout; they cannot change label mode
 * because `htmlLabels` is secured at the top level.
 */
const SECURE_KEYS = [
  "secure",
  "securityLevel",
  "startOnLoad",
  "maxTextSize",
  "suppressErrorRendering",
  "maxEdges",
  "htmlLabels",
  "theme",
  "themeVariables",
  "fontFamily",
  "themeCSS",
  "dompurifyConfig",
  "darkMode",
  "look",
  "arrowMarkerAbsolute",
];

export interface MermaidRenderResult {
  svg: string;
  /** The id Mermaid used inside `svg` (form `mmd<n>z`); callers rescope it. */
  renderId: string;
}

/** The subset of mermaid's default export this runtime relies on. */
export interface MermaidModule {
  initialize(config: Record<string, unknown>): void;
  render(id: string, text: string): Promise<{ svg: string }>;
}

export interface MermaidRuntimeOptions {
  load: () => Promise<MermaidModule>;
  yieldToMain?: () => Promise<void>;
  removeTempElement?: (renderId: string) => void;
  cacheCapacity?: number;
  /** Per-job deadline in milliseconds (default `MERMAID_JOB_TIMEOUT_MS`). */
  jobTimeoutMs?: number;
}

export interface MermaidRuntime {
  peek(
    source: string,
    theme: MermaidThemeConfig
  ): MermaidRenderResult | undefined;
  /**
   * Aborting `signal` withdraws this caller. A queued job with no remaining
   * caller is skipped; the promise then rejects with an `AbortError`.
   */
  render(
    source: string,
    theme: MermaidThemeConfig,
    signal?: AbortSignal
  ): Promise<MermaidRenderResult>;
}

interface InFlightEntry {
  promise: Promise<MermaidRenderResult>;
  /** Callers still waiting; a caller without a signal never leaves. */
  subscribers: number;
}

/** Marks a job whose deadline passed so it stops before touching Mermaid. */
interface JobToken {
  expired: boolean;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function abortError(): Error {
  const error = new Error("The render was cancelled.");
  error.name = "AbortError";
  return error;
}

export function buildMermaidConfig(
  theme: MermaidThemeConfig
): Record<string, unknown> {
  return {
    startOnLoad: false,
    securityLevel: "strict",
    suppressErrorRendering: true,
    theme: "base",
    themeVariables: theme.themeVariables,
    fontFamily: theme.fontFamily,
    // SVG <text> labels: no foreignObject, which keeps PNG export untainted,
    // shrinks the XSS surface and matches the server export.
    htmlLabels: false,
    maxTextSize: MERMAID_MAX_SOURCE_CHARS,
    maxEdges: MERMAID_MAX_EDGES,
    secure: SECURE_KEYS,
  };
}

function defaultYield(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function defaultRemoveTempElement(renderId: string): void {
  if (typeof document === "undefined") return;
  document.getElementById(`d${renderId}`)?.remove();
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "";
}

function noop(): void {}

export function createMermaidRuntime(
  options: MermaidRuntimeOptions
): MermaidRuntime {
  const cache = new LruCache<string, MermaidRenderResult>(
    options.cacheCapacity ?? CACHE_CAPACITY
  );
  const inFlight = new Map<string, InFlightEntry>();
  const jobTimeoutMs = options.jobTimeoutMs ?? MERMAID_JOB_TIMEOUT_MS;
  const yieldToMain = options.yieldToMain ?? defaultYield;
  const removeTempElement =
    options.removeTempElement ?? defaultRemoveTempElement;
  let modulePromise: Promise<MermaidModule> | null = null;
  let initializedKey: string | null = null;
  let tail: Promise<unknown> = Promise.resolve();
  let counter = 0;

  function loadModule(): Promise<MermaidModule> {
    if (!modulePromise) {
      modulePromise = options.load().catch((error: unknown) => {
        modulePromise = null;
        throw error;
      });
    }
    return modulePromise;
  }

  function withDeadline<T>(job: (token: JobToken) => Promise<T>): Promise<T> {
    const token: JobToken = { expired: false };
    let timer: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => {
        token.expired = true;
        reject(
          new MermaidRenderError({
            kind: "render",
            message: TIMEOUT_MESSAGE,
            line: null,
          })
        );
      }, jobTimeoutMs);
    });
    const run = job(token);
    // The job may settle after losing the race; never leave that unhandled.
    run.catch(noop);
    return Promise.race([run, deadline]).finally(() => clearTimeout(timer));
  }

  function enqueue<T>(job: (token: JobToken) => Promise<T>): Promise<T> {
    const run = tail.then(() =>
      withDeadline(async (token) => {
        await yieldToMain();
        return job(token);
      })
    );
    tail = run.then(noop, noop);
    return run;
  }

  async function prepare(theme: MermaidThemeConfig): Promise<MermaidModule> {
    let mermaid: MermaidModule;
    try {
      mermaid = await loadModule();
    } catch (error) {
      throw new MermaidRenderError({
        kind: "render",
        message: messageOf(error),
        line: null,
      });
    }
    if (initializedKey !== theme.key) {
      mermaid.initialize(buildMermaidConfig(theme));
      initializedKey = theme.key;
    }
    return mermaid;
  }

  function cacheKey(source: string, theme: MermaidThemeConfig): string {
    return `${theme.key}\u0000${source}`;
  }

  function tooLarge(source: string): boolean {
    return source.length > MERMAID_MAX_SOURCE_CHARS;
  }

  return {
    peek(source, theme) {
      return cache.get(cacheKey(source, theme));
    },

    render(source, theme, signal) {
      const key = cacheKey(source, theme);
      const cached = cache.get(key);
      if (cached) return Promise.resolve(cached);
      if (tooLarge(source)) {
        return Promise.reject(
          new MermaidRenderError({ kind: "too_large", message: "", line: null })
        );
      }
      if (signal?.aborted) return Promise.reject(abortError());

      let entry = inFlight.get(key);
      if (!entry) {
        const created = { subscribers: 0 } as InFlightEntry;
        created.promise = enqueue(async (token) => {
          if (created.subscribers === 0) throw abortError();
          const mermaid = await prepare(theme);
          if (token.expired) throw abortError();
          counter += 1;
          const renderId = `mmd${counter}z`;
          try {
            const { svg } = await mermaid.render(renderId, source);
            const result: MermaidRenderResult = { svg, renderId };
            cache.set(key, result);
            return result;
          } catch (error) {
            throw new MermaidRenderError(toMermaidDiagnostic(error, source));
          } finally {
            removeTempElement(renderId);
          }
        }).finally(() => {
          if (inFlight.get(key) === created) inFlight.delete(key);
        });
        inFlight.set(key, created);
        entry = created;
      }

      const shared = entry;
      shared.subscribers += 1;
      if (signal) {
        signal.addEventListener(
          "abort",
          () => {
            shared.subscribers -= 1;
          },
          { once: true }
        );
      }
      return shared.promise;
    },
  };
}

let sharedRuntime: MermaidRuntime | null = null;

/** The app-wide runtime. Creating it does not import mermaid. */
export function getMermaidRuntime(): MermaidRuntime {
  if (!sharedRuntime) {
    sharedRuntime = createMermaidRuntime({
      load: async () => {
        const { default: mermaid } = await import("mermaid");
        return mermaid;
      },
    });
  }
  return sharedRuntime;
}
