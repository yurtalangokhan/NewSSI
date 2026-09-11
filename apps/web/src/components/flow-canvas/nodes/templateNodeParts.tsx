/**
 * Presentational sub-components of `TemplateNode` — the card frame, header,
 * inline-editable description and per-handle row. Extracted from
 * `TemplateNode.tsx` so the node factory there stays focused on wiring
 * (hooks, store, drag/connect state) rather than layout. Layout classes are
 * still upstream Langflow's, carried verbatim (see TemplateNode.tsx header).
 */

"use client";

import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import {
  SvgCheck,
  SvgEdit,
  SvgInfo,
  SvgLock,
  SvgPlayCircle,
  SvgWorkflow,
  SvgX,
} from "@opal/icons";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import IconButton from "@/refresh-components/buttons/IconButton";
import InputTextArea from "@/refresh-components/inputs/InputTextArea";
import { FIELD_RENDERERS } from "../fields";
import type { NodeRunStatus } from "../stores/flowStore";
import type {
  Handle as HandleSpec,
  InputField,
} from "../types/componentTemplate";
import type { ValidationIssue } from "../types/flow";
import { resolveComponentIcon } from "../utils/resolveComponentIcon";
import { NodeHandle } from "./NodeHandle";
import Text from "@/refresh-components/texts/Text";

/** upstream :562-568 — the card. `w-80` and the radius/shadow pair are
 * upstream's; the border colour switches to our danger token when the
 * backend validator flagged this node (Task 28). */
export function NodeCard({
  selected,
  hasErrors,
  readOnly,
  runStatus,
  children,
  testId,
}: {
  readOnly?: boolean;
  selected?: boolean;
  hasErrors?: boolean;
  runStatus?: NodeRunStatus | null;
  children: React.ReactNode;
  testId: string;
}) {
  const isRunning = runStatus?.status === "running";
  const isDone = runStatus?.status === "done";
  const isError = runStatus?.status === "error";

  return (
    <div
      data-testid={testId}
      className={cn(
        "generic-node-div group/node relative w-80 rounded-xl border bg-card shadow-sm transition-all duration-200 pointer-events-auto",
        !readOnly && "hover:shadow-md",
        readOnly && "cursor-default select-none",
        isRunning && "border-primary ring-2 ring-primary/40 shadow-md",
        isDone && "border-theme-green-02 ring-1 ring-theme-green-02",
        isError && "border-destructive ring-2 ring-destructive/40",
        hasErrors
          ? "border-destructive"
          : selected
            ? "border-ring ring-1 ring-ring"
            : !isRunning && !isDone && !isError && "border-canvas-border"
      )}
    >
      {children}
    </div>
  );
}

/** upstream :605-640 — icon, then name, in a `px-4 py-3` header that
 * carries the card's only internal `border-b`. */
export function NodeHeader({
  icon,
  title,
  errors,
  onRun,
  isRunning,
  onExpandAgent,
}: {
  icon: string | null | undefined;
  title: string;
  errors: ValidationIssue[];
  onRun?: () => void;
  isRunning?: boolean;
  onExpandAgent?: () => void;
}) {
  const { t } = useTranslation();
  const Icon = resolveComponentIcon(icon);
  return (
    <div
      data-testid="div-generic-node"
      className="flex w-full flex-1 items-center justify-between gap-2 overflow-hidden px-4 py-3"
    >
      <div className="flex items-center overflow-hidden">
        {/* upstream nodeIcon/index.tsx:37-44 — h-4.5 w-4.5 in a centring box */}
        <div className="flex h-[1.125rem] w-[1.125rem] shrink-0 items-center justify-center">
          <Icon className="h-[1.125rem] w-[1.125rem] text-canvas-fg" />
        </div>
        <div className="ml-3 flex flex-1 overflow-hidden">
          <span className="truncate text-sm font-medium text-canvas-fg">
            {title}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {onRun && !isRunning && (
          <IconButton
            icon={SvgPlayCircle}
            tooltip={t("flowCanvas.nodeToolbar.run", "Run")}
            aria-label={t("flowCanvas.nodeToolbar.run", "Run")}
            small
            className="nodrag"
            onClick={(e) => {
              e.stopPropagation();
              onRun();
            }}
          />
        )}
        {onExpandAgent && (
          <IconButton
            icon={SvgWorkflow}
            tooltip={t(
              "flowCanvas.nodeToolbar.expandAgent",
              "Expand into flow"
            )}
            aria-label={t(
              "flowCanvas.nodeToolbar.expandAgent",
              "Expand into flow"
            )}
            small
            className="nodrag"
            onClick={(e) => {
              e.stopPropagation();
              onExpandAgent();
            }}
          />
        )}
        {errors.length > 0 && (
          <SimpleTooltip tooltip={errors.map((e) => e.message).join(" ")}>
            <div
              data-testid="node-error-badge"
              className="h-2 w-2 shrink-0 rounded-full bg-destructive"
            />
          </SimpleTooltip>
        )}
      </div>
    </div>
  );
}

export function NodeDescription({
  description,
  onSave,
  readOnly = false,
}: {
  description: string;
  onSave: (newDesc: string) => void;
  readOnly?: boolean;
}) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(description);

  function handleSave() {
    setIsEditing(false);
    onSave(draft);
  }

  function handleCancel() {
    setIsEditing(false);
    setDraft(description);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSave();
    } else if (e.key === "Escape") {
      handleCancel();
    }
  }

  if (isEditing) {
    return (
      <div className="nodrag px-4 pb-3">
        <div className="flex flex-col gap-1.5 rounded-md border border-input bg-background p-1.5 shadow-sm">
          <InputTextArea
            variant="internal"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            autoFocus
            className="bg-transparent p-0 text-xs"
            placeholder={t(
              "flowCanvas.inspector.descriptionPlaceholder",
              "Enter component description..."
            )}
          />
          <div className="flex items-center justify-end gap-1">
            <IconButton
              icon={SvgX}
              small
              onClick={handleCancel}
              aria-label={t("flowCanvas.fields.prompt.cancel", "Cancel")}
            />
            <IconButton
              icon={SvgCheck}
              action
              primary
              small
              onClick={handleSave}
              aria-label={t("flowCanvas.inspector.saveDescription", "Save")}
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="group/desc relative px-4 pb-3">
      <div className="flex items-start justify-between gap-1">
        <Text as="p" className="text-sm text-muted-foreground line-clamp-2">
          {description || t("flowCanvas.node.noDescription", "No description.")}
        </Text>
        {!readOnly && (
          <IconButton
            icon={SvgEdit}
            small
            className="nodrag shrink-0 opacity-0 transition-opacity group-hover/desc:opacity-100"
            aria-label={t(
              "flowCanvas.nodeToolbar.editDescription",
              "Edit description"
            )}
            onClick={() => {
              setDraft(description);
              setIsEditing(true);
            }}
          />
        )}
      </div>
    </div>
  );
}

/** upstream renders each handle inside the row it belongs to, so the dot
 * sits on the card's border level with its label rather than stacking at
 * the card's centre. The row is `relative` and the handle absolute, which
 * is what lets xyflow measure each one's real position.
 *
 * The label is a field label (`text-canvas-fg`, medium), not muted body
 * text — in Langflow a port row reads as "Tools", "Input", "Response",
 * the same weight as a parameter's own label. */
export function HandleRow({
  handle,
  direction,
  connected,
  field,
  fieldKey,
  value,
  onFieldChange,
  isPotentialTarget,
  onHandleClick,
  componentType,
}: {
  handle: HandleSpec;
  direction: "source" | "target";
  connected?: boolean;
  field?: InputField;
  /** The values key `field` writes to. Defaults to the handle's own name;
   * a port declaring `fallback_field` names a differently-keyed field. */
  fieldKey?: string;
  value?: unknown;
  onFieldChange?: (key: string, value: unknown) => void;
  isPotentialTarget?: boolean;
  onHandleClick?: () => void;
  componentType?: string;
}) {
  const { t } = useTranslation();
  const left = direction === "target";
  const Renderer = field ? FIELD_RENDERERS[field.type] : undefined;
  const fallbackLabel =
    field?.display_name ||
    (handle.name
      ? handle.name.charAt(0).toUpperCase() + handle.name.slice(1)
      : "");
  const label = field?.display_name
    ? t(
        [
          `flowCanvas.fields.names.${handle.name}`,
          `flowCanvas.handles.${handle.name}`,
        ],
        field.display_name
      )
    : t(`flowCanvas.handles.${handle.name}`, fallbackLabel);
  const infoKey = fieldKey ?? handle.name;
  const info = field?.info
    ? t(
        componentType
          ? [
              `flowCanvas.fields.infos.${componentType}.${infoKey}`,
              `flowCanvas.fields.infos.${infoKey}`,
              `flowCanvas.fields.infos.${handle.name}`,
            ]
          : [
              `flowCanvas.fields.infos.${infoKey}`,
              `flowCanvas.fields.infos.${handle.name}`,
            ],
        field.info
      )
    : undefined;

  return (
    <div className="relative px-4 py-1.5">
      <NodeHandle
        handle={handle}
        direction={direction}
        isPotentialTarget={isPotentialTarget}
        onHandleClick={onHandleClick}
      />
      <div
        className={cn(
          "flex items-center",
          left ? "justify-start" : "justify-end"
        )}
      >
        <span className="truncate text-sm font-medium text-canvas-fg">
          {label}
          {field?.required && <span className="text-destructive">*</span>}
        </span>
        {field?.info && (
          <SimpleTooltip tooltip={info || field.info}>
            <span className="ml-1 cursor-help text-muted-foreground">
              <SvgInfo className="h-3 w-3" />
            </span>
          </SimpleTooltip>
        )}
      </div>
      {left &&
        (connected ? (
          <div
            data-testid={`port-state-${handle.name}`}
            className="mt-1 flex h-8 items-center gap-1.5 rounded-md border border-canvas-border bg-muted px-2 text-sm text-muted-foreground"
          >
            <SvgLock className="h-3 w-3 shrink-0" />
            <span className="truncate">
              {t("flowCanvas.nodeHandle.receiving", "Receiving {{label}}", {
                label,
              })}
            </span>
          </div>
        ) : field && Renderer && onFieldChange ? (
          <div className="nodrag mt-1">
            <Renderer
              fieldKey={fieldKey ?? handle.name}
              field={field}
              value={value !== undefined ? value : field.value}
              onChange={(v) => onFieldChange(fieldKey ?? handle.name, v)}
            />
          </div>
        ) : (
          <div
            data-testid={`port-state-${handle.name}`}
            className="mt-1 flex h-8 items-center gap-1.5 rounded-md border border-canvas-border bg-muted px-2 text-sm text-muted-foreground"
          >
            <span className="truncate">
              {t(
                "flowCanvas.nodeHandle.connectSource",
                "Connect a {{types}} source",
                { types: handle.types.join(" / ") }
              )}
            </span>
          </div>
        ))}
    </div>
  );
}
