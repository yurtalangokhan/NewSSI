"use client";

import { useCallback, useState } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  SvgChevronDown,
  SvgChevronLeft,
  SvgChevronRight,
  SvgChevronUp,
} from "@opal/icons";
import { useTranslation } from "react-i18next";

import type {
  OrganizationFlowNode as OrganizationFlowNodeType,
  OrganizationLayoutOrientation,
} from "@/components/organization/organizationGraph";
import {
  organizationMemberDetail,
  organizationMemberInitials,
  organizationMemberName,
} from "@/components/organization/organizationMembers";
import {
  SvgEdit,
  SvgFolderPlus,
  SvgLock,
  SvgNetworkGraph,
  SvgOrganization,
  SvgTrash,
  SvgX,
} from "@/icons";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface OrganizationHandlesProps {
  orientation?: OrganizationLayoutOrientation;
}

function OrganizationHandles({
  orientation = "vertical",
}: OrganizationHandlesProps) {
  const handleClass = (active: boolean) =>
    cn(
      "!h-2 !w-2 !border-background-neutral-00 !bg-text-04 transition-opacity duration-200 motion-reduce:transition-none",
      active ? "!opacity-100" : "!opacity-30"
    );
  const vertical = orientation === "vertical";

  return (
    <>
      <Handle
        id="top"
        className={handleClass(vertical)}
        isConnectable={false}
        position={Position.Top}
        type="target"
      />
      <Handle
        id="bottom"
        className={handleClass(vertical)}
        isConnectable={false}
        position={Position.Bottom}
        type="source"
      />
      <Handle
        id="left"
        className={handleClass(!vertical)}
        isConnectable={false}
        position={Position.Left}
        type="target"
      />
      <Handle
        id="right"
        className={handleClass(!vertical)}
        isConnectable={false}
        position={Position.Right}
        type="source"
      />
    </>
  );
}

export function OrganizationFlowNode({
  id,
  data,
  selected,
}: NodeProps<OrganizationFlowNodeType>) {
  const { t } = useTranslation();
  const [draftName, setDraftName] = useState("");
  const [editName, setEditName] = useState(data.name);
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

  const submitRename = useCallback(async () => {
    const name = editName.trim();
    if (!name || name === data.name || isSubmitting || !data.onRename) return;
    setIsSubmitting(true);
    try {
      await data.onRename(name);
      data.onCancelAction?.();
    } finally {
      setIsSubmitting(false);
    }
  }, [data, editName, isSubmitting]);

  const submitDelete = useCallback(async () => {
    if (isSubmitting || !data.onDelete) return;
    setIsSubmitting(true);
    try {
      await data.onDelete();
      data.onCancelAction?.();
    } finally {
      setIsSubmitting(false);
    }
  }, [data, isSubmitting]);

  if (data.isDraft) {
    return (
      <div
        aria-label={t("admin.organizations.designer.newChild")}
        className={cn(
          "nodrag nopan w-64 rounded-12 border border-dashed border-action-link-05 bg-background-neutral-00 p-3 ring-1 ring-action-link-05"
        )}
      >
        <OrganizationHandles orientation={data.layoutOrientation} />
        <div className={cn("flex items-center gap-1")}>
          <InputTypeIn
            aria-label={t("admin.organizations.tree.childNameLabel")}
            autoFocus
            placeholder={t("admin.organizations.tree.namePlaceholder")}
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
            aria-label={t("admin.organizations.actions.cancelNew")}
            icon={SvgX}
            small
            tertiary
            tooltip={t("admin.organizations.actions.cancel")}
            onClick={() => data.onCancelDraft?.()}
          />
        </div>
      </div>
    );
  }

  if (data.actionMode === "delete") {
    return (
      <div
        aria-label={t("admin.organizations.designer.deleteConfirmation", {
          name: data.name,
        })}
        className={cn(
          "nodrag nopan w-64 rounded-12 border border-status-error-03 bg-background-neutral-00 p-4"
        )}
      >
        <OrganizationHandles orientation={data.layoutOrientation} />
        <Text mainUiAction text04 as="p">
          {t("admin.organizations.designer.deleteQuestion")}
        </Text>
        <Text secondaryBody text03 as="p" className={cn("mt-1 truncate")}>
          {data.name}
        </Text>
        <div className={cn("mt-3 flex items-center gap-2")}>
          <Button
            aria-label={t("admin.organizations.actions.deleteNamed", {
              name: data.name,
            })}
            danger
            secondary
            size="md"
            disabled={isSubmitting}
            onClick={() => void submitDelete()}
          >
            {t("admin.organizations.actions.delete")}
          </Button>
          <Button
            secondary
            size="md"
            disabled={isSubmitting}
            onClick={() => data.onCancelAction?.()}
          >
            {t("admin.organizations.actions.cancel")}
          </Button>
        </div>
      </div>
    );
  }

  const totalChildCount = data.childCount || (data.childrenCount as number) || 0;
  const hasSubItems = Boolean(data.hasChildren || totalChildCount > 0);
  const childLabel = t("admin.organizations.designer.childCount", {
    count: totalChildCount,
  });

  return (
    <div
      aria-label={t("admin.organizations.designer.organizationLabel", {
        name: data.name,
      })}
      data-selected={selected ? "true" : "false"}
      data-search-state={
        data.searchMatch ? "match" : data.searchDimmed ? "dimmed" : "idle"
      }
      data-testid={`organization-flow-node-${id}`}
      className={cn(
        "relative w-64 rounded-12 border bg-background-neutral-00 p-4 shadow-none transition-[opacity,background-color,border-color,box-shadow] duration-200 motion-reduce:transition-none",
        data.searchMatch &&
          "border-action-link-05 bg-background-neutral-03 ring-2 ring-action-link-05 shadow-md",
        data.searchDimmed && "opacity-30",
        data.isDropTarget &&
          "border-status-success-03 bg-background-neutral-03 ring-2 ring-status-success-03",
        selected
          ? "border-action-link-05 ring-1 ring-action-link-05"
          : "border-border-02"
      )}
    >
      <OrganizationHandles orientation={data.layoutOrientation} />
      <div className={cn("flex items-start gap-3")}>
        <div
          className={cn(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-8 bg-background-neutral-02 text-text-03"
          )}
        >
          <SvgOrganization size={16} />
        </div>
        <div className={cn("min-w-0 flex-1")}>
          {data.actionMode === "rename" ? (
            <div className={cn("nodrag nopan flex flex-col gap-2")}>
              <div className={cn("flex items-center gap-1")}>
                <InputTypeIn
                  aria-label={t(
                    "admin.organizations.designer.organizationNameFor",
                    {
                      name: data.name,
                    }
                  )}
                  autoFocus
                  showClearButton={false}
                  value={editName}
                  variant={isSubmitting ? "disabled" : "primary"}
                  onChange={(event) => setEditName(event.target.value)}
                  onKeyDown={(event) => {
                    event.stopPropagation();
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void submitRename();
                    } else if (event.key === "Escape") {
                      event.preventDefault();
                      setEditName(data.name);
                      data.onCancelAction?.();
                    }
                  }}
                />
                <IconButton
                  aria-label={t("admin.organizations.actions.cancelRename", {
                    name: data.name,
                  })}
                  icon={SvgX}
                  small
                  tertiary
                  tooltip={t("admin.organizations.actions.cancel")}
                  onClick={() => {
                    setEditName(data.name);
                    data.onCancelAction?.();
                  }}
                />
              </div>
              <InputSelect
                value={data.parentId ?? ""}
                disabled={data.parentId === null}
                onValueChange={(parentId) => data.onRequestMove?.(parentId)}
              >
                <InputSelect.Trigger
                  aria-label={t("admin.organizations.inspector.moveTo")}
                />
                <InputSelect.Content>
                  {(data.parentOptions ?? []).map((parent) => (
                    <InputSelect.Item key={parent.id} value={parent.id}>
                      {parent.name}
                    </InputSelect.Item>
                  ))}
                </InputSelect.Content>
              </InputSelect>
            </div>
          ) : (
            <Text mainUiAction text04 as="p" className={cn("truncate")}>
              {data.name}
            </Text>
          )}
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
              {t("admin.organizations.designer.positionLocked")}
            </Text>
          </div>
        )}
        {(data.canAddChild || (data.canManage && !data.actionMode)) && (
          <div
            data-testid="organization-node-actions"
            className={cn("ml-auto flex items-center gap-0.5")}
          >
            {data.canAddChild && (
              <IconButton
                aria-label={t("admin.organizations.actions.addChildTo", {
                  name: data.name,
                })}
                className={cn("nodrag nopan")}
                icon={SvgFolderPlus}
                small
                tertiary
                tooltip={t("admin.organizations.actions.addChild")}
                onClick={() => data.onAddChild?.()}
              />
            )}
            {data.canManage && !data.actionMode && (
              <>
                <IconButton
                  aria-label={t("admin.organizations.actions.renameNamed", {
                    name: data.name,
                  })}
                  className={cn("nodrag nopan")}
                  icon={SvgEdit}
                  small
                  tertiary
                  tooltip={t("admin.organizations.actions.rename")}
                  onClick={() => data.onBeginRename?.()}
                />
                <IconButton
                  aria-label={t("admin.organizations.actions.deleteNamed", {
                    name: data.name,
                  })}
                  className={cn("nodrag nopan")}
                  danger
                  icon={SvgTrash}
                  small
                  tertiary
                  tooltip={t("admin.organizations.actions.delete")}
                  onClick={() => data.onBeginDelete?.()}
                />
              </>
            )}
          </div>
        )}
      </div>
      {data.members && data.members.length > 0 && (
        <div
          data-testid={`organization-members-${id}`}
          className={cn(
            "nodrag nopan mt-3 max-h-28 overflow-y-auto rounded-08 border border-border-01 bg-background-neutral-02 p-1.5"
          )}
        >
          {data.members.slice(0, 4).map((member) => (
            <div
              key={member.id}
              className={cn("flex min-w-0 items-center gap-2 px-1 py-1")}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-background-neutral-04 font-secondary-mono text-[10px] text-text-05"
                )}
              >
                {organizationMemberInitials(member)}
              </span>
              <div className={cn("min-w-0 flex-1")}>
                <Text
                  secondaryBody
                  text04
                  className={cn("block truncate text-xs")}
                >
                  {organizationMemberName(member)}
                </Text>
                <Text
                  secondaryBody
                  text02
                  className={cn("block truncate text-[10px]")}
                >
                  {organizationMemberDetail(member)}
                </Text>
              </div>
            </div>
          ))}
          {data.members.length > 4 && (
            <Text
              secondaryMono
              text03
              className={cn("block px-1 pt-1 text-xs")}
            >
              {t("admin.organizations.tree.moreMembers", {
                count: data.members.length - 4,
              })}
            </Text>
          )}
        </div>
      )}

      {/* Modern Expand Subtree Button */}
      {hasSubItems && (
        <button
          type="button"
          aria-label={
            data.isSubtreeExpanded
              ? t("admin.organizations.designer.collapseSubtree", {
                  defaultValue: "Collapse sub-items",
                  name: data.name,
                })
              : t("admin.organizations.designer.expandSubtree", {
                  defaultValue: "Expand sub-items",
                  name: data.name,
                })
          }
          data-testid={`toggle-subtree-${id}`}
          className={cn(
            "nodrag nopan absolute z-10 flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs shadow-sm transition-all duration-200 hover:scale-105 hover:border-action-link-05 hover:text-action-link-05 hover:shadow-md motion-reduce:transition-none",
            data.layoutOrientation === "horizontal"
              ? "-right-3.5 top-1/2 -translate-y-1/2 translate-x-1/2"
              : "-bottom-3.5 left-1/2 -translate-x-1/2",
            data.isSubtreeExpanded
              ? "border-border-02 bg-background-neutral-00 text-text-03"
              : "border-action-link-05 bg-background-neutral-03 text-action-link-05 font-medium shadow-md ring-1 ring-action-link-05"
          )}
          onClick={(event) => {
            event.stopPropagation();
            data.onToggleSubtree?.();
          }}
        >
          {data.layoutOrientation === "horizontal" ? (
            data.isSubtreeExpanded ? (
              <SvgChevronLeft size={12} />
            ) : (
              <SvgChevronRight size={12} />
            )
          ) : data.isSubtreeExpanded ? (
            <SvgChevronUp size={12} />
          ) : (
            <SvgChevronDown size={12} />
          )}
          <span className="font-secondary-mono text-[11px] font-semibold leading-none">
            {data.childCount}
          </span>
        </button>
      )}
    </div>
  );
}
