import type { MiniMapNodeProps } from "@xyflow/react";

// A constant screen-space outline keeps distant nodes visible on large maps.
export function OrganizationMiniMapNode({
  id,
  x,
  y,
  width,
  height,
  color,
  selected,
  onClick,
}: MiniMapNodeProps) {
  return (
    <rect
      x={x}
      y={y}
      width={width}
      height={height}
      fill={color}
      stroke={selected ? "var(--theme-primary-05)" : "var(--theme-primary-04)"}
      strokeWidth={selected ? 4 : 2}
      vectorEffect="non-scaling-stroke"
      onClick={(event) => onClick?.(event, id)}
    />
  );
}
