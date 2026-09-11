/**
 * Ported from Langflow (MIT) —
 * vendor/langflow/pages/FlowPage/components/ConnectionLineComponent/index.tsx
 *
 * The line that follows the cursor while dragging a new connection: a
 * 2px animated cubic path plus a white dot with a coloured rim at the
 * cursor end. Path expression, stroke width and the r=5 / strokeWidth=1.5
 * dot are upstream's verbatim.
 *
 * Upstream colours it from `flowStore.handleDragging.color` — a value
 * their store writes when a drag starts. We don't track drag state in the
 * store (Task 22 pushed connection validity into `isValidConnection`
 * instead), so the colour comes from the source handle's own port type,
 * resolved through the same `portColors` map the handles themselves use.
 * Same signal, read from the handle rather than from a store field.
 */

"use client";

import type { ConnectionLineComponentProps } from "@xyflow/react";
import { portColor } from "../utils/portColors";
import type { CanvasNode } from "../types/flow";
import type { ComponentType } from "react";
import { findTemplateByType } from "../utils/findTemplate";
import type { GroupedComponentTemplates } from "../types/componentTemplate";

export function createConnectionLine(
  getGrouped: () => GroupedComponentTemplates | undefined
): ComponentType<ConnectionLineComponentProps<CanvasNode>> {
  return function ConnectionLine({
    fromX,
    fromY,
    toX,
    toY,
    fromNode,
    fromHandle,
    connectionLineStyle = {},
  }: ConnectionLineComponentProps<CanvasNode>) {
    const grouped = getGrouped();
    // xyflow hands the connection line an `InternalNode`, whose `data` is
    // the untyped base `Record<string, unknown>`; the node itself is ours.
    const node = fromNode as unknown as CanvasNode | undefined;
    const template =
      grouped && node ? findTemplateByType(grouped, node.data.type) : undefined;
    const handleName = fromHandle?.id ?? undefined;
    const types =
      template && handleName
        ? [...template.handles.outputs, ...template.handles.inputs].find(
            (h) => h.name === handleName
          )?.types
        : undefined;
    const accentColor = portColor(types ?? []);

    return (
      <g>
        <path
          fill="none"
          strokeWidth={2}
          className="animated"
          style={{ stroke: accentColor, ...connectionLineStyle }}
          d={`M${fromX},${fromY} C ${fromX} ${toY} ${fromX} ${toY} ${toX},${toY}`}
        />
        <circle
          cx={toX}
          cy={toY}
          fill="#fff"
          r={5}
          stroke={accentColor}
          strokeWidth={1.5}
        />
      </g>
    );
  };
}
