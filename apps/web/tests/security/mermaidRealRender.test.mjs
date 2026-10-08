/**
 * Security regression suite against the REAL mermaid renderer.
 *
 * Jest maps `mermaid` to a stand-in, so nothing there proves the hardening
 * (strict security level, secured keys, sanitising) holds against the library
 * itself. This runs under `node --test` with jsdom globals and executes the
 * production runtime + sanitiser on hostile diagrams.
 *
 *   node --experimental-transform-types --import ./tests/security/register.mjs \
 *     --test tests/security/mermaidRealRender.test.mjs
 */
import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>", { pretendToBeVisual: true });
for (const key of [
  "window", "document", "navigator", "Element", "HTMLElement", "SVGElement",
  "Node", "DOMParser", "MutationObserver", "CSSStyleSheet",
]) {
  Object.defineProperty(globalThis, key, {
    value: dom.window[key] ?? class { insertRule() {} },
    configurable: true,
    writable: true,
  });
}
// jsdom has no SVG layout; fixed metrics are enough for mermaid to lay out.
dom.window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 60, height: 20 });
dom.window.SVGElement.prototype.getComputedTextLength = () => 60;

const { createMermaidRuntime, buildMermaidConfig } = await import("@/components/mermaid/mermaidRuntime.ts");
const { sanitizeMermaidSvg } = await import("@/components/mermaid/mermaidSanitize.ts");
const { SERVER_MERMAID_THEME } = await import("@/components/mermaid/mermaidTheme.ts");

const DANGEROUS = /javascript:|<script|\son\w+\s*=|<foreignObject|<iframe/i;

let runtime;
before(() => {
  runtime = createMermaidRuntime({ load: async () => (await import("mermaid")).default });
});

async function renderSanitised(source) {
  const { svg } = await runtime.render(source, SERVER_MERMAID_THEME);
  return { raw: svg, clean: sanitizeMermaidSvg(svg) };
}

function assertInert({ raw, clean }, label) {
  assert.ok(clean.includes("<svg"), "diagram must still render");
  assert.ok(clean.includes(label), "label text must survive");
  assert.doesNotMatch(raw, DANGEROUS, "raw mermaid output must already be inert");
  assert.doesNotMatch(clean, DANGEROUS, "sanitised output must be inert");
}

describe("real mermaid hardening", () => {
  it("production config pins strict security and secures the overridable keys", () => {
    const config = buildMermaidConfig(SERVER_MERMAID_THEME);
    assert.equal(config.securityLevel, "strict");
    assert.equal(config.htmlLabels, false);
    for (const key of ["securityLevel", "htmlLabels", "themeCSS", "dompurifyConfig"]) {
      assert.ok(config.secure.includes(key), `${key} must be secured`);
    }
  });

  it("ignores an in-diagram %%{init}%% that requests securityLevel loose", async () => {
    const result = await renderSanitised(
      '%%{init: {"securityLevel":"loose","htmlLabels":true}}%%\n' +
        'flowchart TD\n  A["Start <img src=x onerror=alert(1)>"] --> B[End]\n  click A call alert(1)'
    );
    assertInert(result, "End");
  });

  it("neutralises nested HTML in labels", async () => {
    const result = await renderSanitised(
      'flowchart TD\n  A["<b><i><script>alert(1)</script><a href=\'javascript:alert(1)\'>x</a></i></b>"] --> B[Done]'
    );
    assertInert(result, "Done");
  });

  it("drops `click … href` javascript: links", async () => {
    const result = await renderSanitised(
      'flowchart TD\n  A[Go] --> B[Next]\n  click A href "javascript:alert(document.cookie)"'
    );
    assertInert(result, "Next");
  });

  it("drops `click … call` callbacks", async () => {
    const result = await renderSanitised('flowchart TD\n  A[Go] --> B[Next]\n  click A call alert("x")');
    assertInert(result, "Next");
  });

  // Runs last: it re-initialises the shared mermaid singleton without the hardening.
  it("control: the same click-href diagram is NOT inert without the hardening", async () => {
    const mermaid = (await import("mermaid")).default;
    mermaid.initialize({ startOnLoad: false, securityLevel: "loose", suppressErrorRendering: true });
    const { svg } = await mermaid.render(
      "control",
      'flowchart TD\n  A[Go] --> B[Next]\n  click A href "javascript:alert(1)"'
    );
    assert.match(svg, DANGEROUS, "detector must fire on an unhardened render");
  });
});
