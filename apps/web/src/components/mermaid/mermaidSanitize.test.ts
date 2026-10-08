/**
 * @jest-environment jsdom
 */
import { sanitizeMermaidSvg } from "@/components/mermaid/mermaidSanitize";

// Shaped like Mermaid's flowchart output: style block, marker defs, clusters,
// edge paths, text labels, and the root accessibility attributes.
const DIAGRAM =
  '<svg id="mmd1z" width="100%" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100" style="max-width: 200px;" role="graphics-document document" aria-roledescription="flowchart-v2">' +
  "<title>Order flow</title><desc>Two steps</desc>" +
  '<style>#mmd1z{font-family:"Hanken Grotesk";fill:#333}#mmd1z .label text{fill:#333}</style>' +
  '<g><marker id="mmd1z_flowchart-v2-pointEnd" class="marker flowchart-v2" viewBox="0 0 10 10" refX="5" refY="5" markerUnits="userSpaceOnUse" markerWidth="8" markerHeight="8" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" class="arrowMarkerPath"></path></marker></g>' +
  '<g class="root"><g class="edgePaths"><path d="M10,10L90,10" id="L_A_B_0" class="flowchart-link" marker-end="url(#mmd1z_flowchart-v2-pointEnd)"></path></g>' +
  '<g class="node default" id="flowchart-A-0" data-id="A" transform="translate(50, 20)"><rect class="basic label-container" x="-20" y="-10" width="40" height="20"></rect><g class="label" transform="translate(-10, -8)"><text><tspan x="0" dy="1em">Start</tspan></text></g></g></g>' +
  "</svg>";

describe("sanitizeMermaidSvg", () => {
  it("keeps everything a Mermaid diagram needs", () => {
    const out = sanitizeMermaidSvg(DIAGRAM);

    expect(out).toContain('xmlns="http://www.w3.org/2000/svg"');
    expect(out).toContain('viewBox="0 0 200 100"');
    expect(out).toContain("<title>Order flow</title>");
    expect(out).toContain("<desc>Two steps</desc>");
    expect(out).toContain("#mmd1z .label text{fill:#333}");
    expect(out).toMatch(/<marker[^>]*id="mmd1z_flowchart-v2-pointEnd"/);
    expect(out).toMatch(/refX="5"/i);
    expect(out).toContain('marker-end="url(#mmd1z_flowchart-v2-pointEnd)"');
    expect(out).toContain('id="flowchart-A-0"');
    expect(out).toContain('transform="translate(50, 20)"');
    expect(out).toContain('<tspan x="0" dy="1em">Start</tspan>');
    expect(out).toContain('aria-roledescription="flowchart-v2"');
  });

  it("drops foreignObject, scripts, event handlers and javascript: links", () => {
    const hostile =
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">' +
      '<foreignObject><div onclick="alert(1)">x</div></foreignObject>' +
      "<script>alert(1)</script>" +
      '<a href="javascript:alert(1)"><text onload="alert(2)">t</text></a>' +
      '<rect onmouseover="alert(3)" width="1" height="1"></rect></svg>';

    const out = sanitizeMermaidSvg(hostile);

    expect(out).not.toMatch(/foreignobject/i);
    expect(out).not.toContain("<script");
    expect(out).not.toMatch(/on\w+=/i);
    expect(out).not.toContain("javascript:");
    expect(out).toContain("<rect");
  });
});
