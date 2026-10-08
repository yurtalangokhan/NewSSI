import {
  createSvgScopeId,
  pngScale,
  readSvgAccessibleName,
  readSvgSize,
  rescopeSvgIds,
  withPixelSize,
} from "@/components/mermaid/mermaidSvg";

const SVG =
  '<svg id="mmd1z" width="100%" xmlns="http://www.w3.org/2000/svg" style="max-width: 316.9px;" viewBox="-8 -8 316.9 174"><style>#mmd1z .node{}</style><marker id="mmd1z_arrow"></marker><text>mmd11z</text></svg>';

const SEQUENCE_SVG =
  '<svg id="mmd1z" viewBox="0 0 400 300"><defs><filter id="drop-shadow"></filter></defs><use href="#actor1"></use><g id="actor1" aria-labelledby="actor-label1"></g><text id="actor-label1">Alice</text><g id="actor-man-actor1-circle"></g><g id="root-1"></g></svg>';

describe("rescopeSvgIds", () => {
  it("leaves data-id bookkeeping alone while rescoping real ids", () => {
    const svg =
      '<svg id="mmd1z" data-id="mmd1z"><g data-id="mmd1z_arrow"><marker id="mmd1z_arrow"></marker><use href="#mmd1z_arrow"></use></g></svg>';

    const out = rescopeSvgIds(svg, "mmd1z", "mmdv7z");

    expect(out).toContain('id="mmdv7z"');
    expect(out).toContain('id="mmdv7z_arrow"');
    expect(out).toContain('href="#mmdv7z_arrow"');
    // Mermaid's own bookkeeping keeps pointing at the ids it was written for.
    expect(out.match(/data-id="mmd1z"/g)).toHaveLength(1);
    expect(out).toContain('data-id="mmd1z_arrow"');
  });

  it("moves every id and selector to the new scope without touching longer ids", () => {
    const out = rescopeSvgIds(SVG, "mmd1z", "mmdv7z");

    expect(out).toContain('id="mmdv7z"');
    expect(out).toContain("#mmdv7z .node");
    expect(out).toContain('id="mmdv7z_arrow"');
    expect(out).toContain("<text>mmd11z</text>");
    expect(rescopeSvgIds(SVG, "mmd1z", "mmd1z")).toBe(SVG);
  });

  it("rescopes unprefixed sequence diagram ids and their references", () => {
    const out = rescopeSvgIds(SEQUENCE_SVG, "mmd1z", "mmdv2z");

    expect(out).toContain('id="mmdv2z-drop-shadow"');
    expect(out).toContain('id="mmdv2z-actor1"');
    expect(out).toContain('id="mmdv2z-actor-label1"');
    expect(out).toContain('id="mmdv2z-actor-man-actor1-circle"');
    expect(out).toContain('id="mmdv2z-root-1"');
    expect(out).toContain('href="#mmdv2z-actor1"');
    expect(out).toContain('aria-labelledby="mmdv2z-actor-label1"');
  });

  it("escapes regex-special ids instead of throwing or over-matching", () => {
    const svg =
      '<svg id="mmd1z" viewBox="0 0 10 10"><style>#mmd1z.a\\(b\\)[c]{}</style>' +
      '<g id="a.b(c)[d]+e*f"></g><use href="#a.b(c)[d]+e*f"></use></svg>';

    expect(() => rescopeSvgIds(svg, "mmd1z", "mmdv9z")).not.toThrow();
    const out = rescopeSvgIds(svg, "mmd1z", "mmdv9z");
    expect(out).toContain('id="mmdv9z-a.b(c)[d]+e*f"');
    expect(out).toContain('href="#mmdv9z-a.b(c)[d]+e*f"');
  });

  it("matches ids exactly, not as a prefix of a longer id", () => {
    const svg =
      '<svg id="mmd1z" viewBox="0 0 10 10"><style>#actor1{fill:red}#actor10{fill:blue}</style>' +
      '<g id="actor1"></g><g id="actor10"></g></svg>';

    const out = rescopeSvgIds(svg, "mmd1z", "mmdv9z");

    expect(out).toContain('id="mmdv9z-actor1"');
    expect(out).toContain('id="mmdv9z-actor10"');
    expect(out).toContain("#mmdv9z-actor1{fill:red}");
    expect(out).toContain("#mmdv9z-actor10{fill:blue}");
    expect(out).not.toContain("#mmdv9z-actor1-actor10");
  });

  it("rewrites a CSS selector but leaves matching text content untouched", () => {
    const svg =
      '<svg id="mmd1z" viewBox="0 0 10 10"><style>#actor1{fill:red}</style>' +
      '<g id="actor1"></g><text>#actor1</text></svg>';

    const out = rescopeSvgIds(svg, "mmd1z", "mmdv9z");

    expect(out).toContain("#mmdv9z-actor1{fill:red}");
    expect(out).toContain("<text>#actor1</text>");
  });

  it("rescopes every id of a large diagram in one pass", () => {
    const count = 2000;
    const idAttrs: string[] = [];
    for (let i = 0; i < count; i += 1) idAttrs.push(`<g id="node${i}"></g>`);
    const svg = `<svg id="mmd1z" viewBox="0 0 10 10">${idAttrs.join("")}</svg>`;

    const out = rescopeSvgIds(svg, "mmd1z", "mmdv9z");

    expect(out).toContain('id="mmdv9z-node0"');
    expect(out).toContain(`id="mmdv9z-node${count - 1}"`);
    expect(out).not.toContain('id="node');
  });

  it("does not treat id= or url(#...) text inside a label as an id or reference", () => {
    const svg =
      '<svg id="mmd1z" viewBox="0 0 10 10"><g id="real"></g>' +
      '<text>say id="ghost" and url(#real) and data-id="real"</text>' +
      '<rect data-id="real" filter="url(#real)"></rect></svg>';

    const out = rescopeSvgIds(svg, "mmd1z", "mmdv9z");

    expect(out).toContain('<g id="mmdv9z-real"></g>');
    expect(out).toContain(
      '<text>say id="ghost" and url(#real) and data-id="real"</text>'
    );
    expect(out).toContain('data-id="real" filter="url(#mmdv9z-real)"');
    expect(out).not.toContain("mmdv9z-ghost");
  });

  it("creates distinct scope ids that never contain each other", () => {
    const a = createSvgScopeId();
    const b = createSvgScopeId();

    expect(a).toMatch(/^mmdv\d+z$/);
    expect(b).not.toBe(a);
    expect(b.includes(a)).toBe(false);
  });
});

describe("readSvgAccessibleName", () => {
  it("joins the title and description and decodes entities", () => {
    expect(
      readSvgAccessibleName(
        '<svg><title id="t">Orders &amp; refunds</title><desc>Two steps</desc></svg>'
      )
    ).toBe("Orders & refunds. Two steps");
  });

  it("falls back to whichever exists, else null", () => {
    expect(readSvgAccessibleName("<svg><desc>Only desc</desc></svg>")).toBe(
      "Only desc"
    );
    expect(readSvgAccessibleName("<svg><title> </title></svg>")).toBeNull();
    expect(readSvgAccessibleName("<svg></svg>")).toBeNull();
  });
});

describe("readSvgSize", () => {
  it("reads the viewBox size, including negative origins and decimals", () => {
    expect(readSvgSize(SVG)).toEqual({ width: 316.9, height: 174 });
  });

  it("returns null without a usable viewBox", () => {
    expect(readSvgSize("<svg></svg>")).toBeNull();
    expect(readSvgSize('<svg viewBox="0 0 0 10"></svg>')).toBeNull();
    expect(readSvgSize("not svg")).toBeNull();
  });
});

describe("pngScale", () => {
  it("uses 2x for normal diagrams and caps huge ones at the canvas side limit", () => {
    expect(pngScale({ width: 300, height: 200 })).toBe(2);
    expect(pngScale({ width: 6000, height: 100 })).toBeCloseTo(8192 / 6000);
  });

  it("respects both per-side and area limits", () => {
    // Per-side limit: 8192 / 6000 ≈ 1.365
    const sideLimited = pngScale({ width: 6000, height: 100 });
    expect(sideLimited).toBeCloseTo(8192 / 6000);

    // Area limit: sqrt(16777216 / (5000 * 5000)) ≈ 0.820
    // Per-side limit: 8192 / 5000 = 1.638
    // Result uses the tighter constraint (area)
    const areaLimited = pngScale({ width: 5000, height: 5000 });
    expect(areaLimited).toBeCloseTo(Math.sqrt(16777216 / (5000 * 5000)));
    expect(areaLimited * 5000 * areaLimited * 5000).toBeLessThanOrEqual(
      16777216
    );
  });

  it("never exceeds maxSide regardless of diagram size", () => {
    const scale = pngScale({ width: 100000, height: 100000 });
    expect(scale * 100000).toBeLessThanOrEqual(8192);
  });
});

describe("withPixelSize", () => {
  it("replaces width=100% with explicit pixel dimensions on the root only", () => {
    const out = withPixelSize(SVG, { width: 316.9, height: 174 });

    expect(out.startsWith('<svg width="316.9" height="174" id="mmd1z"')).toBe(
      true
    );
    expect(out).not.toContain('width="100%"');
    expect(out).toContain('viewBox="-8 -8 316.9 174"');
  });
});
