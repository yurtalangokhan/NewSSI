import {
  classifyPullError,
  parseSseLine,
  recordLayerProgress,
} from "./ModelDownloadModal";

describe("parseSseLine", () => {
  it("returns null for non-data lines", () => {
    expect(parseSseLine("")).toBeNull();
    expect(parseSseLine(": comment")).toBeNull();
  });

  it("returns null for malformed JSON instead of throwing", () => {
    expect(parseSseLine("data: not json")).toBeNull();
  });

  it("parses a normal progress frame", () => {
    expect(parseSseLine('data: {"status":"pulling manifest"}')).toEqual({
      status: "pulling manifest",
    });
  });

  it("surfaces the 'error' field Ollama sends for an unknown model name, so it isn't mistaken for a normal status update", () => {
    expect(
      parseSseLine('data: {"error":"pull model manifest: file does not exist"}')
    ).toEqual({ error: "pull model manifest: file does not exist" });
  });
});

describe("recordLayerProgress", () => {
  it("ignores events without a digest/total (e.g. 'pulling manifest', 'verifying digest')", () => {
    const layers = new Map();
    expect(
      recordLayerProgress(layers, { status: "pulling manifest" })
    ).toBeNull();
    expect(
      recordLayerProgress(layers, { status: "verifying sha256 digest" })
    ).toBeNull();
  });

  it("sums bytes across every layer digest seen so far, instead of resetting on each new layer", () => {
    const layers = new Map();

    // Layer 1 downloads to completion.
    recordLayerProgress(layers, {
      status: "pulling abc123",
      digest: "abc123",
      completed: 1000,
      total: 1000,
    });

    // Ollama starts layer 2 — a naive reading of just this event would show
    // progress dropping from 100% back down to 0%.
    const afterLayer2Starts = recordLayerProgress(layers, {
      status: "pulling def456",
      digest: "def456",
      completed: 0,
      total: 4000,
    });

    // Overall completed/total should reflect BOTH layers combined, so the
    // percentage the UI derives from this never goes backward.
    expect(afterLayer2Starts).toEqual({ completed: 1000, total: 5000 });

    const afterLayer2Progresses = recordLayerProgress(layers, {
      status: "pulling def456",
      digest: "def456",
      completed: 2000,
      total: 4000,
    });
    expect(afterLayer2Progresses).toEqual({ completed: 3000, total: 5000 });
  });
});

describe("classifyPullError", () => {
  it("classifies the real Ollama 'unknown model' error text as notFound", () => {
    expect(classifyPullError("pull model manifest: file does not exist")).toBe(
      "notFound"
    );
  });

  it("classifies a differently-worded not-found message as notFound too", () => {
    expect(
      classifyPullError(
        'model "totally-bogus-model" not found, try pulling it first'
      )
    ).toBe("notFound");
  });

  it("is case-insensitive", () => {
    expect(classifyPullError("Pull Model Manifest: File Does Not Exist")).toBe(
      "notFound"
    );
  });

  it("falls back to generic for unrecognized error text", () => {
    expect(classifyPullError("connection reset by peer")).toBe("generic");
  });
});
