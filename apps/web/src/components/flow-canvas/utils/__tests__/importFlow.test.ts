import { parseFlowJson } from "../importFlow";

describe("parseFlowJson — failure codes", () => {
  it("returns invalidJson for malformed JSON text", () => {
    const r = parseFlowJson("{ not json");
    expect(r.success).toBe(false);
    if (!r.success) expect(r.errorCode).toBe("invalidJson");
  });

  it("returns notAnObject for a non-object primitive", () => {
    const r = parseFlowJson(42 as unknown);
    expect(r.success).toBe(false);
    if (!r.success) expect(r.errorCode).toBe("notAnObject");
  });

  it("returns missingSpec when the parsed value has no spec object", () => {
    const r = parseFlowJson(JSON.stringify("hello"));
    expect(r.success).toBe(false);
    if (!r.success) expect(r.errorCode).toBe("missingSpec");
  });

  it("returns noNodes for an object with an empty spec", () => {
    const r = parseFlowJson(JSON.stringify({ nodes: [], edges: [] }));
    expect(r.success).toBe(false);
    if (!r.success) expect(r.errorCode).toBe("noNodes");
  });
});
