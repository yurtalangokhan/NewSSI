/**
 * OrganizationTree Component
 *
 * Enterprise-grade hierarchical organization tree management with:
 * - Drag & drop support
 * - Inline editing
 * - Context menu actions
 * - Permission visualization
 * - User assignment
 *
 * Uses react-arborist for high-performance tree rendering.
 *
 * @requires react-arborist (run: npm install react-arborist)
 */

"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { Tree, NodeRendererProps } from "react-arborist";
import { useTranslation } from "react-i18next";
import type { OrganizationNode } from "@/components/organization/organizationTypes";
import { SvgEdit, SvgFolderPlus, SvgMaximize2, SvgTrash, SvgX } from "@/icons";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface OrganizationTreeProps {
  organizations: OrganizationNode[];
  onCreateOrg: (parentId: string | null, name: string) => Promise<void>;
  onUpdateOrg: (
    id: string,
    updates: Partial<OrganizationNode>
  ) => Promise<void>;
  onDeleteOrg: (id: string) => Promise<void>;
  onMoveOrg: (id: string, newParentId: string | null) => Promise<void>;
  onSelectOrg: (org: OrganizationNode) => void;
  onOpenDesigner?: () => void;
  selectedOrgId?: string | null;
  className?: string;
}

interface OrganizationNodeRendererProps
  extends NodeRendererProps<OrganizationNode> {
  onCreateOrg: (parentId: string | null, name: string) => Promise<void>;
  onUpdateOrg: (
    id: string,
    updates: Partial<OrganizationNode>
  ) => Promise<void>;
  onDeleteOrg: (id: string) => Promise<void>;
}

interface InlineOrganizationCreateProps {
  ariaLabel: string;
  parentId: string | null;
  onCancel: () => void;
  onCreateOrg: (parentId: string | null, name: string) => Promise<void>;
  placeholder: string;
}

function InlineOrganizationCreate({
  ariaLabel,
  parentId,
  onCancel,
  onCreateOrg,
  placeholder,
}: InlineOrganizationCreateProps) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = useCallback(async () => {
    const trimmedName = name.trim();
    if (!trimmedName || isSubmitting) return;

    setIsSubmitting(true);
    try {
      await onCreateOrg(parentId, trimmedName);
      onCancel();
    } finally {
      setIsSubmitting(false);
    }
  }, [isSubmitting, name, onCancel, onCreateOrg, parentId]);

  return (
    <div
      className={cn("flex min-w-0 flex-1 items-center gap-1")}
      onClick={(event) => event.stopPropagation()}
    >
      <InputTypeIn
        aria-label={ariaLabel}
        autoFocus
        className={cn("min-w-0 flex-1")}
        placeholder={placeholder}
        showClearButton={false}
        value={name}
        variant={isSubmitting ? "disabled" : "primary"}
        onChange={(event) => setName(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            void handleSubmit();
          } else if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
          }
        }}
      />
      <IconButton
        aria-label={t("admin.organizations.actions.cancelNew")}
        icon={SvgX}
        small
        tertiary
        tooltip={t("admin.organizations.actions.cancel")}
        onClick={onCancel}
      />
    </div>
  );
}

function Node({
  node,
  style,
  dragHandle,
  onCreateOrg,
  onUpdateOrg,
  onDeleteOrg,
}: OrganizationNodeRendererProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [isCreatingChild, setIsCreatingChild] = useState(false);
  const [editName, setEditName] = useState(node.data.name);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSave = useCallback(() => {
    if (editName.trim() && editName !== node.data.name) {
      void onUpdateOrg(node.data.id, { name: editName.trim() });
    }
    setIsEditing(false);
  }, [editName, node, onUpdateOrg]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        handleSave();
      } else if (e.key === "Escape") {
        setEditName(node.data.name);
        setIsEditing(false);
      }
    },
    [handleSave, node.data.name]
  );

  return (
    <div style={style} ref={dragHandle}>
      <div
        className={cn(
          "group flex min-w-0 items-center gap-2 rounded-md px-3 py-2 cursor-pointer transition-colors",
          "hover:bg-background-neutral-02",
          node.isSelected &&
            "bg-background-primary-01 border border-border-primary"
        )}
        onClick={() => node.isInternal && node.toggle()}
      >
        {/* Expand/Collapse Icon */}
        {node.isInternal ? (
          <div
            className={cn("flex h-4 w-4 items-center justify-center")}
            aria-hidden="true"
          >
            {node.isOpen ? "−" : "+"}
          </div>
        ) : (
          <div className={cn("w-4")} />
        )}

        {/* Name (editable) */}
        {isEditing ? (
          <InputTypeIn
            ref={inputRef}
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onBlur={handleSave}
            onKeyDown={handleKeyDown}
            className={cn("flex-1")}
            autoFocus
          />
        ) : (
          <Text
            className={cn(
              "min-w-0 flex-1 truncate text-sm font-medium text-text-01"
            )}
          >
            {node.data.name}
          </Text>
        )}

        {/* Metadata badges */}
        <div
          className={cn(
            "ml-auto flex shrink-0 items-center gap-1 transition-opacity"
          )}
        >
          {node.data.user_count !== undefined && node.data.user_count > 0 && (
            <div
              className={cn(
                "flex items-center gap-1 px-2 py-1 rounded bg-background-neutral-02"
              )}
            >
              <Text className={cn("text-xs text-text-03")}>
                {node.data.user_count}
              </Text>
            </div>
          )}

          <IconButton
            icon={SvgEdit}
            tooltip={t("admin.organizations.actions.rename")}
            tertiary
            small
            aria-label={t("admin.organizations.actions.renameNamed", {
              name: node.data.name,
            })}
            onClick={(event) => {
              event.stopPropagation();
              setIsEditing(true);
            }}
          />
          <IconButton
            icon={SvgFolderPlus}
            tooltip={t("admin.organizations.actions.addChild")}
            tertiary
            small
            aria-label={t("admin.organizations.actions.addChildTo", {
              name: node.data.name,
            })}
            onClick={(event) => {
              event.stopPropagation();
              setIsCreatingChild(true);
            }}
          />
          <IconButton
            icon={SvgTrash}
            tooltip={t("admin.organizations.actions.delete")}
            danger
            tertiary
            small
            aria-label={t("admin.organizations.actions.deleteNamed", {
              name: node.data.name,
            })}
            onClick={(event) => {
              event.stopPropagation();
              if (confirm(`Delete "${node.data.name}"?`)) {
                void onDeleteOrg(node.data.id);
              }
            }}
          />
        </div>
      </div>
      {isCreatingChild && (
        <div
          className={cn(
            "absolute left-8 right-0 top-full z-20 flex items-center rounded-md border border-border-02 bg-background-neutral-00 px-3 py-1 shadow-sm"
          )}
        >
          <InlineOrganizationCreate
            ariaLabel={t("admin.organizations.tree.childNameLabel")}
            parentId={node.data.id}
            placeholder={t("admin.organizations.tree.childPlaceholder")}
            onCancel={() => setIsCreatingChild(false)}
            onCreateOrg={onCreateOrg}
          />
        </div>
      )}
    </div>
  );
}

export function OrganizationTree({
  organizations,
  onCreateOrg,
  onUpdateOrg,
  onDeleteOrg,
  onMoveOrg,
  onSelectOrg,
  onOpenDesigner,
  selectedOrgId,
  className,
}: OrganizationTreeProps) {
  const { t } = useTranslation();
  const [isCreating, setIsCreating] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [treeHeight, setTreeHeight] = useState(600);

  // Update tree height when container resizes
  useEffect(() => {
    const updateHeight = () => {
      if (containerRef.current) {
        const height = containerRef.current.clientHeight;
        if (height > 0) {
          setTreeHeight(height);
        }
      }
    };

    // Initial measurement
    updateHeight();

    // Set up resize observer
    const resizeObserver = new ResizeObserver(updateHeight);
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  const handleMove = useCallback(
    async ({
      dragIds,
      parentId,
    }: {
      dragIds: string[];
      parentId: string | null;
      parentNode?: any;
    }) => {
      if (parentId === null) return;

      for (const id of dragIds) {
        await onMoveOrg(id, parentId);
      }
    },
    [onMoveOrg]
  );

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Header */}
      <div
        className={cn(
          "flex items-center justify-between p-4 border-b border-border-02"
        )}
      >
        <div className={cn("flex items-center gap-2")}>
          <Text className={cn("text-lg font-semibold text-text-01")}>
            {t("admin.organizations.tree.title")}
          </Text>
        </div>

        <div className={cn("flex items-center gap-2")}>
          {onOpenDesigner && (
            <IconButton
              icon={SvgMaximize2}
              tooltip={t("admin.organizations.tree.openDesigner")}
              aria-label={t("admin.organizations.tree.openDesigner")}
              tertiary
              onClick={onOpenDesigner}
            />
          )}
        </div>
      </div>

      {/* Tree */}
      <div ref={containerRef} className={cn("flex-1 overflow-hidden p-4")}>
        {organizations.length === 0 ? (
          <div
            className={cn(
              "flex flex-col items-center justify-center h-full text-center"
            )}
          >
            <Text className={cn("text-text-02 mb-2")}>
              {t("admin.organizations.tree.emptyTitle")}
            </Text>
            <Text className={cn("text-text-03 text-sm mb-4")}>
              {t("admin.organizations.tree.emptyDescription")}
            </Text>
            {isCreating ? (
              <div className={cn("w-full max-w-sm")}>
                <InlineOrganizationCreate
                  ariaLabel={t("admin.organizations.tree.rootNameLabel")}
                  parentId={null}
                  placeholder={t("admin.organizations.tree.namePlaceholder")}
                  onCancel={() => setIsCreating(false)}
                  onCreateOrg={onCreateOrg}
                />
              </div>
            ) : (
              <Button
                action
                primary
                size="md"
                onClick={() => setIsCreating(true)}
              >
                {t("admin.organizations.tree.create")}
              </Button>
            )}
          </div>
        ) : (
          <Tree
            data={organizations}
            openByDefault={false}
            initialOpenState={Object.fromEntries(
              organizations.map((organization) => [organization.id, true])
            )}
            width="100%"
            height={treeHeight}
            indent={24}
            rowHeight={40}
            overscanCount={10}
            selection={selectedOrgId ?? undefined}
            onSelect={(nodes) => {
              const node = nodes[0];
              if (node) {
                onSelectOrg(node.data);
              }
            }}
            onMove={handleMove}
          >
            {(props) => (
              <Node
                {...props}
                onCreateOrg={onCreateOrg}
                onUpdateOrg={onUpdateOrg}
                onDeleteOrg={onDeleteOrg}
              />
            )}
          </Tree>
        )}
      </div>
    </div>
  );
}
