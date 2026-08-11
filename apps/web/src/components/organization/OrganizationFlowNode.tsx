"use client";

import { useCallback, useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

import type { OrganizationFlowNode as OrganizationFlowNodeType } from "@/components/organization/organizationGraph";
import {
  SvgFolderPlus,
  SvgLock,
  SvgNetworkGraph,
  SvgOrganization,
  SvgX,
} from "@/icons";
import IconButton from "@/refresh-components/buttons/IconButton";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

export function OrganizationFlowNode({
  id,
  data,
  selected,
}: NodeProps<OrganizationFlowNodeType>) {
  const [draftName, setDraftName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submitDraft = useCallback(async () => {
    const name = draftName.trim();
    if (!name || isSubmitting || !data.onSubmitDraft) return;
    setIsSubmitting(true);
    try {
      await data.onSubmitDraft(name);
    } finally {
      setIsSubmitting(false);
    }
  }, [data, draftName, isSubmitting]);

  if (data.isDraft) {
    return (
      <div
        aria-label="New child organization"
        className={cn(
          "nodrag nopan w-64 rounded-12 border border-dashed border-action-link-05 bg-background-neutral-00 p-3 ring-1 ring-action-link-05"
        )}
      >
        <Handle isConnectable={false} position={Position.Top} type="target" />
        <div className={cn("flex items-center gap-1")}>
          <InputTypeIn
            aria-label="New child organization name"
            autoFocus
            placeholder="Organization name"
            showClearButton={false}
            value={draftName}
            variant={isSubmitting ? "disabled" : "primary"}
            onChange={(event) => setDraftName(event.target.value)}
            onKeyDown={(event) => {
              event.stopPropagation();
              if (event.key === "Enter") {
                event.preventDefault();
                void submitDraft();
              } else if (event.key === "Escape") {
                event.preventDefault();
                data.onCancelDraft?.();
              }
            }}
          />
          <IconButton
            aria-label="Cancel new organization"
            icon={SvgX}
            small
            tertiary
            tooltip="Cancel"
            onClick={() => data.onCancelDraft?.()}
          />
        </div>
      </div>
    );
  }

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
              Position locked
            </Text>
          </div>
        )}
        {data.canAddChild && (
          <IconButton
            aria-label={`Add child to ${data.name}`}
            className={cn("nodrag nopan")}
            icon={SvgFolderPlus}
            small
            tertiary
            tooltip="Add child"
            onClick={() => data.onAddChild?.()}
          />
        )}
      </div>
      <Handle isConnectable={false} position={Position.Bottom} type="source" />
    </div>
  );
}
