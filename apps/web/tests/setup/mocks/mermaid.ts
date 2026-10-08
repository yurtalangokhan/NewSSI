/**
 * Jest stand-in for the `mermaid` package (mapped in jest.config.js).
 *
 * jsdom has no SVG layout (no getBBox / getComputedTextLength), so the real
 * renderer cannot run under Jest. Real rendering is covered by Playwright
 * (tests/e2e/chat/mermaid_rendering.spec.ts).
 *
 * Contract: a line containing BROKEN fails with Mermaid's jison-style
 * "Parse error on line N:" message. Anything else renders a tiny SVG whose
 * root id is the render id and which embeds that id in a marker, like the
 * real output does.
 */
interface MockRenderResult {
  svg: string;
  diagramType: string;
}

function firstBrokenLine(text: string): number | null {
  const lines = text.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    if (lines[index]!.includes("BROKEN")) return index + 1;
  }
  return null;
}

function parseErrorFor(line: number): Error {
  return new Error(
    `Parse error on line ${line}:\n...BROKEN...\n---^\nExpecting 'SEMI', got 'BROKEN'`
  );
}

const mermaidMock = {
  initialize: jest.fn(),
  render: jest.fn(
    async (id: string, text: string): Promise<MockRenderResult> => {
      const broken = firstBrokenLine(text);
      if (broken !== null) throw parseErrorFor(broken);
      return {
        svg: `<svg id="${id}" xmlns="http://www.w3.org/2000/svg" width="100%" style="max-width: 200px;" viewBox="0 0 200 100"><defs><marker id="${id}_arrow"></marker></defs><g></g></svg>`,
        diagramType: "flowchart-v2",
      };
    }
  ),
  parse: jest.fn(async (text: string) => {
    const broken = firstBrokenLine(text);
    if (broken !== null) throw parseErrorFor(broken);
    return { diagramType: "flowchart-v2", config: {} };
  }),
};

export default mermaidMock;
