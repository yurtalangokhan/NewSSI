import {
  MERMAID_MAX_EDGES,
  createMermaidRuntime,
  type MermaidModule,
} from "@/components/mermaid/mermaidRuntime";
import { MERMAID_MAX_SOURCE_CHARS } from "@/components/mermaid/mermaidSource";
import { buildMermaidTheme } from "@/components/mermaid/mermaidTheme";

const LIGHT = buildMermaidTheme(
  (token) => (token === "--text-05" ? "#000000e5" : ""),
  { darkMode: false, fontFamily: "Hanken Grotesk" }
);
const DARK = buildMermaidTheme(
  (token) => (token === "--text-05" ? "#fffffff2" : ""),
  { darkMode: true, fontFamily: "Hanken Grotesk" }
);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

function fakeMermaid() {
  const calls: string[] = [];
  const fake: MermaidModule = {
    initialize: jest.fn((config: Record<string, unknown>) => {
      const variables = config.themeVariables as { darkMode: boolean };
      calls.push(`init:${variables.darkMode}`);
    }),
    render: jest.fn(async (id: string, text: string) => {
      calls.push(`render:${text}`);
      return { svg: `<svg id="${id}"></svg>` };
    }),
  };
  return { module: fake, calls };
}

function runtimeWith(
  module: MermaidModule,
  load = jest.fn(async () => module)
) {
  const yieldToMain = jest.fn(() => Promise.resolve());
  const removeTempElement = jest.fn();
  const runtime = createMermaidRuntime({
    load,
    yieldToMain,
    removeTempElement,
  });
  return { runtime, load, yieldToMain, removeTempElement };
}

describe("createMermaidRuntime", () => {
  it("does not load mermaid until the first render, then loads it once", async () => {
    const { module } = fakeMermaid();
    const { runtime, load } = runtimeWith(module);
    expect(load).not.toHaveBeenCalled();

    await runtime.render("flowchart LR\n  A --> B", LIGHT);
    await runtime.render("flowchart LR\n  B --> C", LIGHT);

    expect(load).toHaveBeenCalledTimes(1);
  });

  it("initializes once per theme with strict, label-safe, capped config", async () => {
    const { module } = fakeMermaid();
    const { runtime } = runtimeWith(module);

    await runtime.render("A", LIGHT);
    await runtime.render("B", LIGHT);
    await runtime.render("C", DARK);

    expect(module.initialize).toHaveBeenCalledTimes(2);
    const config = (module.initialize as jest.Mock).mock.calls[0]![0];
    expect(config).toMatchObject({
      startOnLoad: false,
      securityLevel: "strict",
      suppressErrorRendering: true,
      theme: "base",
      htmlLabels: false,
      maxTextSize: MERMAID_MAX_SOURCE_CHARS,
      maxEdges: MERMAID_MAX_EDGES,
      themeVariables: LIGHT.themeVariables,
    });
    expect(config.secure).toEqual(
      expect.arrayContaining([
        "securityLevel",
        "maxTextSize",
        "maxEdges",
        "htmlLabels",
        "theme",
        "themeVariables",
      ])
    );
  });

  it("runs initialize+render as one unit, so a theme switch never interleaves", async () => {
    const { module, calls } = fakeMermaid();
    const gate = deferred<{ svg: string }>();
    (module.render as jest.Mock).mockImplementationOnce(
      async (_id: string, text: string) => {
        calls.push(`render:${text}`);
        return gate.promise;
      }
    );
    const { runtime } = runtimeWith(module);

    const first = runtime.render("A", LIGHT);
    const second = runtime.render("B", DARK);
    await flush();
    expect(calls).toEqual(["init:false", "render:A"]);

    gate.resolve({ svg: "<svg></svg>" });
    await Promise.all([first, second]);
    expect(calls).toEqual(["init:false", "render:A", "init:true", "render:B"]);
  });

  it("yields to the main thread before every job", async () => {
    const { module } = fakeMermaid();
    const { runtime, yieldToMain } = runtimeWith(module);

    await Promise.all([runtime.render("A", LIGHT), runtime.render("B", LIGHT)]);

    expect(yieldToMain).toHaveBeenCalledTimes(2);
  });

  it("caches by source and theme and exposes a synchronous peek", async () => {
    const { module } = fakeMermaid();
    const { runtime } = runtimeWith(module);

    const result = await runtime.render("A", LIGHT);

    expect(runtime.peek("A", LIGHT)).toEqual(result);
    expect(runtime.peek("A", DARK)).toBeUndefined();
    await runtime.render("A", LIGHT);
    expect(module.render).toHaveBeenCalledTimes(1);
  });

  it("shares one in-flight render between identical requests", async () => {
    const { module } = fakeMermaid();
    const { runtime } = runtimeWith(module);

    const [one, two] = await Promise.all([
      runtime.render("A", LIGHT),
      runtime.render("A", LIGHT),
    ]);

    expect(one).toBe(two);
    expect(module.render).toHaveBeenCalledTimes(1);
  });

  it("gives every render a unique id and removes Mermaid's temp element", async () => {
    const { module } = fakeMermaid();
    const { runtime, removeTempElement } = runtimeWith(module);

    const a = await runtime.render("A", LIGHT);
    const b = await runtime.render("B", LIGHT);

    expect(a.renderId).toMatch(/^mmd\d+z$/);
    expect(b.renderId).not.toBe(a.renderId);
    expect(a.svg).toContain(`id="${a.renderId}"`);
    expect(removeTempElement).toHaveBeenCalledWith(a.renderId);
    expect(removeTempElement).toHaveBeenCalledWith(b.renderId);
  });

  it("refuses oversized sources before loading mermaid", async () => {
    const { module } = fakeMermaid();
    const { runtime, load } = runtimeWith(module);

    await expect(
      runtime.render("x".repeat(MERMAID_MAX_SOURCE_CHARS + 1), LIGHT)
    ).rejects.toMatchObject({ diagnostic: { kind: "too_large", line: null } });
    expect(load).not.toHaveBeenCalled();
  });

  it("maps a parse failure to a diagnostic, does not cache it and keeps the queue alive", async () => {
    const { module } = fakeMermaid();
    (module.render as jest.Mock).mockRejectedValueOnce(
      new Error("Parse error on line 2:\nA BROKEN B\n----^\nExpecting 'SEMI'")
    );
    const { runtime, removeTempElement } = runtimeWith(module);

    await expect(
      runtime.render("flowchart\nA BROKEN B", LIGHT)
    ).rejects.toMatchObject({
      diagnostic: { kind: "parse", line: 2, message: "Expecting 'SEMI'" },
    });
    expect(runtime.peek("flowchart\nA BROKEN B", LIGHT)).toBeUndefined();
    expect(removeTempElement).toHaveBeenCalledTimes(1);
    await expect(runtime.render("A", LIGHT)).resolves.toMatchObject({
      svg: expect.stringContaining("<svg"),
    });
  });

  it("retries loading after a failed chunk load", async () => {
    const { module } = fakeMermaid();
    const load = jest
      .fn<Promise<MermaidModule>, []>()
      .mockRejectedValueOnce(new Error("ChunkLoadError"))
      .mockResolvedValue(module);
    const { runtime } = runtimeWith(module, load);

    await expect(runtime.render("A", LIGHT)).rejects.toMatchObject({
      diagnostic: { kind: "render", message: "ChunkLoadError", line: null },
    });
    await expect(runtime.render("A", LIGHT)).resolves.toBeDefined();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("does not let themeCSS, dompurifyConfig or theme keys be overridden by a diagram", async () => {
    const { module } = fakeMermaid();
    const { runtime } = runtimeWith(module);

    await runtime.render("A", LIGHT);

    const config = (module.initialize as jest.Mock).mock.calls[0]![0];
    expect(config.secure).toEqual(
      expect.arrayContaining([
        "themeCSS",
        "dompurifyConfig",
        "darkMode",
        "look",
        "arrowMarkerAbsolute",
      ])
    );
  });

  it("maps the reported line back through front matter and comments", async () => {
    const { module } = fakeMermaid();
    (module.render as jest.Mock).mockRejectedValueOnce(
      new Error("Parse error on line 1:\nA BROKEN B\n^\nExpecting 'SEMI'")
    );
    const { runtime } = runtimeWith(module);
    const source = "---\ntitle: t\n---\n%% note\nflowchart\nA BROKEN B";

    await expect(runtime.render(source, LIGHT)).rejects.toMatchObject({
      diagnostic: { kind: "parse", line: 5 },
    });
  });

  describe("deadline and cancellation", () => {
    afterEach(() => jest.useRealTimers());

    it("releases the queue when a job never settles and reports a render diagnostic", async () => {
      jest.useFakeTimers();
      const { module } = fakeMermaid();
      (module.render as jest.Mock).mockImplementationOnce(
        () => new Promise<never>(() => {})
      );
      const runtime = createMermaidRuntime({
        load: async () => module,
        yieldToMain: () => Promise.resolve(),
        removeTempElement: jest.fn(),
        jobTimeoutMs: 1_000,
      });

      const stuck = runtime.render("stuck", LIGHT);
      const stuckOutcome = stuck.catch((error: unknown) => error);
      const next = runtime.render("next", LIGHT);
      await jest.advanceTimersByTimeAsync(1_000);

      await expect(stuckOutcome).resolves.toMatchObject({
        diagnostic: { kind: "render", line: null },
      });
      await expect(next).resolves.toMatchObject({
        svg: expect.stringContaining("<svg"),
      });
    });

    it("skips a queued job whose only caller aborted", async () => {
      const { module } = fakeMermaid();
      const gate = deferred<{ svg: string }>();
      (module.render as jest.Mock).mockImplementationOnce(
        async () => gate.promise
      );
      const { runtime } = runtimeWith(module);
      const controller = new AbortController();

      const first = runtime.render("A", LIGHT);
      const second = runtime.render("B", LIGHT, controller.signal);
      const secondOutcome = second.catch((error: unknown) => error);
      await flush();
      controller.abort();
      gate.resolve({ svg: "<svg></svg>" });
      await first;

      await expect(secondOutcome).resolves.toMatchObject({
        name: "AbortError",
      });
      expect(module.render).toHaveBeenCalledTimes(1);
    });

    it("still runs a shared job while one caller remains", async () => {
      const { module } = fakeMermaid();
      const gate = deferred<{ svg: string }>();
      (module.render as jest.Mock).mockImplementationOnce(
        async () => gate.promise
      );
      const { runtime } = runtimeWith(module);
      const controller = new AbortController();

      const first = runtime.render("A", LIGHT);
      const one = runtime.render("B", LIGHT, controller.signal);
      const two = runtime.render("B", LIGHT);
      await flush();
      controller.abort();
      gate.resolve({ svg: "<svg></svg>" });
      await first;

      await expect(two).resolves.toMatchObject({
        renderId: expect.any(String),
      });
      await expect(one).resolves.toBeDefined();
      expect(module.render).toHaveBeenCalledTimes(2);
    });

    it("rejects immediately for an already aborted signal", async () => {
      const { module } = fakeMermaid();
      const { runtime, load } = runtimeWith(module);
      const controller = new AbortController();
      controller.abort();

      await expect(
        runtime.render("A", LIGHT, controller.signal)
      ).rejects.toMatchObject({ name: "AbortError" });
      expect(load).not.toHaveBeenCalled();
    });
  });
});
