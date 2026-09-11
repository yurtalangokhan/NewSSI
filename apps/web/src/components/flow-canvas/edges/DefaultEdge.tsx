/**
 * Ported from Langflow (MIT) — vendor/langflow/CustomEdges/index.tsx
 * Upstream: https://github.com/langflow-ai/langflow @ 3ec070e9
 *
 * Langflow does not use xyflow's stock edge. It draws its own path with a
 * hand-tuned curve, offsets the endpoints 7px past the node's edge so the
 * line starts at the handle's outer rim rather than its centre, and puts
 * a delete action behind a right-click on a fat invisible hit-path. All
 * of that geometry is upstream's, carried over verbatim (:44-79).
 *
 * One adaptation: upstream picks the looping path when the *target
 * handle's* JSON descriptor carries `output_types` — that is how their
 * Loop component's back-edge is recognised. Our handles are plain name
 * strings (Tasks 21/23), so there is no descriptor to read. The loop path
 * exists to draw an edge that runs *backwards* across the canvas, so this
 * selects it on that geometric condition instead — same visual outcome
 * for the same case (a Loop node's `continue` edge feeding an earlier
 * node), decided from the geometry rather than a field we don't carry.
 */

"use client";

import {
  BaseEdge,
  getBezierPath,
  Position,
  type EdgeProps,
} from "@xyflow/react";
import { memo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useReactFlow } from "@xyflow/react";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { SvgTrash } from "@opal/icons";

export const DefaultEdge = memo(function DefaultEdge({
  source,
  sourceX,
  sourceY,
  target,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  sourceHandleId,
  targetHandleId,
  id,
  animated,
  selectable,
  deletable,
  selected,
  style,
  markerStart,
  markerEnd,
  interactionWidth,
  className,
  data,
  pathOptions,
  ...rest
}: EdgeProps & { className?: string }) {
  const { t } = useTranslation();
  const { getNode, setEdges } = useReactFlow();

  const sourceNode = getNode(source);
  const targetNode = getNode(target);

  // upstream :45-47 — start/end 7px outside the node box, so the line
  // meets the handle's rim instead of emerging from under the card.
  const sourceXNew =
    (sourceNode?.position.x ?? 0) + (sourceNode?.measured?.width ?? 0) + 7;
  const targetXNew = (targetNode?.position.x ?? 0) - 7;

  // upstream :50-68 — the curve tuning. `zeroOnNegative` eases the control
  // points as the edge flips from forwards to backwards, so a back-edge
  // bows out instead of folding through the nodes.
  const distance = 200 + 0.1 * ((sourceXNew - targetXNew) / 2);
  const zeroOnNegative =
    (1 +
      (1 - Math.exp(-0.01 * Math.abs(sourceXNew - targetXNew))) *
        (sourceXNew - targetXNew >= 0 ? 1 : -1)) /
    2;
  const distanceY =
    200 -
    200 * (1 - zeroOnNegative) +
    0.3 * Math.abs(targetY - sourceY) * zeroOnNegative;
  const sourceDistanceY =
    200 -
    200 * (1 - zeroOnNegative) +
    0.3 * Math.abs(sourceY - targetY) * zeroOnNegative;

  const targetYNew = targetY + 1;
  const sourceYNew = sourceY + 1;

  // upstream :70
  const edgePathLoop = `M ${sourceXNew} ${sourceYNew} C ${
    sourceXNew + distance
  } ${sourceYNew + sourceDistanceY}, ${targetXNew - distance} ${
    targetYNew + distanceY
  }, ${targetXNew} ${targetYNew}`;

  const [edgePath] = getBezierPath({
    sourceX: sourceXNew,
    sourceY: sourceYNew,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    targetX: targetXNew,
    targetY: targetYNew,
  });

  // See the header: geometry stands in for upstream's handle descriptor.
  const isBackEdge = targetXNew < sourceXNew;
  const path = isBackEdge ? edgePathLoop : edgePath;

  const handleDelete = useCallback(() => {
    setEdges((edges) => edges.filter((e) => e.id !== id));
  }, [id, setEdges]);

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={style}
        markerStart={markerStart}
        markerEnd={markerEnd}
        interactionWidth={interactionWidth}
        className={className}
        strokeDasharray={isBackEdge ? "5 5" : "0"}
        data-animated={animated ? "true" : "false"}
        data-selectable={selectable ? "true" : "false"}
        data-deletable={deletable ? "true" : "false"}
        data-selected={selected ? "true" : "false"}
      />

      {/* upstream :102-113 — a 20px-wide transparent path so the edge is
          actually clickable, and the delete action hangs off its menu. */}
      <ContextMenu>
        <ContextMenuTrigger asChild>
          <path
            className="react-flow__edge-interaction"
            d={path}
            strokeOpacity={0}
            strokeWidth={20}
            fill="none"
            data-testid="edge-context-menu-trigger"
          />
        </ContextMenuTrigger>
        <ContextMenuContent>
          <ContextMenuItem
            onClick={handleDelete}
            data-testid="context-menu-item-destructive"
            className="text-destructive focus:text-destructive"
          >
            <SvgTrash className="size-3.5 text-inherit" />
            <span className="text-xs">
              {t("flowCanvas.nodeToolbar.delete", "Delete")}
            </span>
          </ContextMenuItem>
        </ContextMenuContent>
      </ContextMenu>
    </>
  );
});
