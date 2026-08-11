"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { OrganizationFlowNode as OrganizationFlowNodeType } from "@/components/organization/organizationGraph";
import { SvgLock, SvgNetworkGraph, SvgOrganization } from "@/icons";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

export function OrganizationFlowNode({
  id,
  data,
  selected,
}: NodeProps<OrganizationFlowNodeType>) {
  const childLabel = `${data.childCount} ${
    data.childCount === 1 ? "child" : "children"
  }`;

  return (
    <div
      aria-label={`${data.name} organization`}
      data-selected={selected ? "true" : "false"}
      data-testid={`organization-flow-node-${id}`}
      className={cn(
        "w-64 rounded-12 border bg-background-neutral-00 p-4 shadow-none transition-colors",
        selected
          ? "border-action-link-05 ring-1 ring-action-link-05"
          : "border-border-02"
      )}
    >
      <Handle isConnectable={false} position={Position.Top} type="target" />
      <div className={cn("flex items-start gap-3")}>
        <div
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-8 bg-background-neutral-02 text-text-03"
          )}
        >
          <SvgOrganization size={16} />
        </div>
        <div className={cn("min-w-0 flex-1")}>
          <Text mainUiAction text04 as="p" className={cn("truncate")}>
            {data.name}
          </Text>
          <Text secondaryBody text03 as="p" className={cn("mt-1 truncate")}>
            {data.path}
          </Text>
        </div>
      </div>

      <div className={cn("mt-3 flex items-center justify-between gap-3")}>
        <div className={cn("flex items-center gap-1 text-text-03")}>
          <SvgNetworkGraph size={14} />
          <Text secondaryMono text03>
            {childLabel}
          </Text>
        </div>
        {data.readOnly && (
          <div className={cn("flex items-center gap-1 text-text-03")}>
            <SvgLock size={14} />
            <Text secondaryMono text03>
              Read-only
            </Text>
          </div>
        )}
      </div>
      <Handle isConnectable={false} position={Position.Bottom} type="source" />
    </div>
  );
}
