/**
 * Utility to parse and import flow graphs from JSON files or strings.
 * Supports Onyx WireFlowSpec, exported Agent payloads, and generic flow objects.
 */

import type {
  CanvasEdge,
  CanvasNode,
  Viewport,
  WireFlowSpec,
} from "../types/flow";
import { fromFlowSpec } from "./compile";
import { getNodeId } from "./reactflowUtils";

export type ImportErrorCode =
  | "invalidJson"
  | "notAnObject"
  | "missingSpec"
  | "noNodes";

export type ImportFlowResult =
  | {
      success: true;
      graph: {
        nodes: CanvasNode[];
        edges: CanvasEdge[];
        viewport: Viewport;
      };
      spec: WireFlowSpec;
      nodeCount: number;
      edgeCount: number;
    }
  | {
      success: false;
      errorCode: ImportErrorCode;
    };

const DEFAULT_VIEWPORT: Viewport = { x: 0, y: 0, zoom: 1 };

/** A node/edge/spec object straight off untrusted JSON — every field is
 * still `unknown` and must be narrowed before use. */
type RawRecord = Record<string, unknown> & {
  position?: { x?: unknown; y?: unknown };
  data?: RawRecord;
  node?: RawRecord;
  viewport?: { x?: unknown; y?: unknown; zoom?: unknown };
};

const errorMessage = (e: unknown, fallback: string): string =>
  e instanceof Error && e.message ? e.message : fallback;

export function parseFlowJson(rawContent: string | unknown): ImportFlowResult {
  let parsed: RawRecord;
  if (typeof rawContent === "string") {
    try {
      parsed = JSON.parse(rawContent) as RawRecord;
    } catch {
      return { success: false, errorCode: "invalidJson" };
    }
  } else if (typeof rawContent === "object" && rawContent !== null) {
    parsed = rawContent as RawRecord;
  } else {
    return { success: false, errorCode: "notAnObject" };
  }

  // Extract candidate flow spec object
  let rawSpec: RawRecord = parsed;
  if (parsed.flow_spec && typeof parsed.flow_spec === "object") {
    rawSpec = parsed.flow_spec as RawRecord;
  } else if (
    parsed.data &&
    typeof parsed.data === "object" &&
    (parsed.data.nodes || parsed.data.edges)
  ) {
    rawSpec = parsed.data;
  }

  if (!rawSpec || typeof rawSpec !== "object") {
    return { success: false, errorCode: "missingSpec" };
  }

  const rawNodes: RawRecord[] = Array.isArray(rawSpec.nodes)
    ? rawSpec.nodes
    : [];
  const rawEdges: RawRecord[] = Array.isArray(rawSpec.edges)
    ? rawSpec.edges
    : [];

  if (rawNodes.length === 0 && rawEdges.length === 0) {
    return { success: false, errorCode: "noNodes" };
  }

  // Check if nodes have distinct non-zero positions. If not, auto-layout them in a clean grid.
  const hasDistinctPositions =
    rawNodes.length > 1 &&
    rawNodes.some(
      (n: RawRecord) =>
        n.position &&
        typeof n.position.x === "number" &&
        (n.position.x !== 0 || (n.position.y ?? 0) !== 0)
    );

  // Normalize nodes into WireFlowNode format
  const normalizedNodes = rawNodes.map((n: RawRecord, idx: number) => {
    const nodeType = String(
      n.type ||
        n.data?.type ||
        (n.data?.node?.template ? "templateNode" : "ChatInput")
    );
    const id = String(n.id || getNodeId(nodeType));
    const templateVersion =
      typeof n.template_version === "number"
        ? n.template_version
        : typeof n.data?.templateVersion === "number"
          ? n.data.templateVersion
          : 1;

    let posX = 0;
    let posY = 0;
    if (
      hasDistinctPositions &&
      n.position &&
      typeof n.position.x === "number"
    ) {
      posX = n.position.x;
      posY = typeof n.position.y === "number" ? n.position.y : 0;
    } else {
      // Auto-layout: 3-column flow grid with comfortable spacing
      const col = idx % 3;
      const row = Math.floor(idx / 3);
      posX = col * 360 + 100;
      posY = row * 260 + 150;
    }

    // Extract values from n.values, n.data.values, or n.data directly
    let rawValues: unknown = n.values;
    if (!rawValues && n.data && typeof n.data === "object") {
      rawValues = n.data.values || n.data;
    }
    const values: Record<string, unknown> =
      rawValues && typeof rawValues === "object"
        ? (rawValues as Record<string, unknown>)
        : {};

    return {
      id,
      type: nodeType,
      template_version: templateVersion,
      position: { x: posX, y: posY },
      values,
    };
  });

  // Normalize edges into WireFlowEdge format
  const normalizedEdges = rawEdges.map((e: RawRecord) => {
    const id = String(e.id || getNodeId("xy-edge"));
    const source = String(e.source || "");
    const target = String(e.target || "");
    const sourceHandle = String(
      e.sourceHandle || e.data?.sourceHandle || "output"
    );
    const targetHandle = String(
      e.targetHandle || e.data?.targetHandle || "input"
    );

    return {
      id,
      source,
      target,
      sourceHandle,
      targetHandle,
    };
  });

  const viewport: Viewport = {
    x:
      typeof rawSpec.viewport?.x === "number"
        ? rawSpec.viewport.x
        : DEFAULT_VIEWPORT.x,
    y:
      typeof rawSpec.viewport?.y === "number"
        ? rawSpec.viewport.y
        : DEFAULT_VIEWPORT.y,
    zoom:
      typeof rawSpec.viewport?.zoom === "number"
        ? rawSpec.viewport.zoom
        : DEFAULT_VIEWPORT.zoom,
  };

  const spec: WireFlowSpec = {
    version: typeof rawSpec.version === "string" ? rawSpec.version : "1.0",
    nodes: normalizedNodes,
    edges: normalizedEdges,
    viewport,
  };

  const graph = fromFlowSpec(spec);

  return {
    success: true,
    graph,
    spec,
    nodeCount: graph.nodes.length,
    edgeCount: graph.edges.length,
  };
}

export function getJsonSyntaxErrorDetails(rawText: string): {
  message: string;
  line?: number;
  column?: number;
} | null {
  if (!rawText || !rawText.trim()) return null;
  try {
    JSON.parse(rawText);
    return null;
  } catch (err) {
    const message: string = errorMessage(err, "Invalid JSON syntax");
    // Check if error message contains "position X"
    const posMatch = /position\s+(\d+)/i.exec(message);
    if (posMatch && posMatch[1]) {
      const position = parseInt(posMatch[1], 10);
      const before = rawText.slice(0, position);
      const lines = before.split("\n");
      const line = lines.length;
      const lastLine = lines[lines.length - 1] ?? "";
      const column = lastLine.length + 1;
      return { message, line, column };
    }
    // Check if line and column are directly in message (e.g. line X column Y)
    const lineMatch = /line\s+(\d+)/i.exec(message);
    const colMatch = /column\s+(\d+)/i.exec(message);
    if (lineMatch && lineMatch[1]) {
      return {
        message,
        line: parseInt(lineMatch[1], 10),
        column: colMatch && colMatch[1] ? parseInt(colMatch[1], 10) : undefined,
      };
    }
    return { message };
  }
}

export const SAMPLE_FLOW_JSON = JSON.stringify(
  {
    version: "1.0",
    nodes: [
      {
        id: "chat_input_1",
        type: "ChatInput",
        template_version: 1,
        position: { x: 100, y: 200 },
        values: {},
      },
      {
        id: "prompt_1",
        type: "PromptTemplate",
        template_version: 1,
        position: { x: 450, y: 200 },
        values: {
          template: "Answer the user question accurately: {input}",
        },
      },
      {
        id: "chat_output_1",
        type: "ChatOutput",
        template_version: 1,
        position: { x: 800, y: 200 },
        values: {},
      },
    ],
    edges: [
      {
        id: "edge_1",
        source: "chat_input_1",
        target: "prompt_1",
        sourceHandle: "message",
        targetHandle: "input",
      },
      {
        id: "edge_2",
        source: "prompt_1",
        target: "chat_output_1",
        sourceHandle: "prompt",
        targetHandle: "message",
      },
    ],
    viewport: { x: 0, y: 0, zoom: 1 },
  },
  null,
  2
);
