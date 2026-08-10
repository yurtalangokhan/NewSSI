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
import { SvgEdit, SvgFolderPlus, SvgTrash } from "@opal/icons";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface OrganizationNode {
  id: string;
  name: string;
  path: string;
  parent_id: string | null;
  description?: string;
  metadata?: Record<string, any>;
  children?: OrganizationNode[];
  user_count?: number;
  permission_count?: number;
}

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
  selectedOrgId?: string | null;
  className?: string;
}

interface OrganizationNodeRendererProps
  extends NodeRendererProps<OrganizationNode> {
  onCreateOrg: (parentId: string | null) => Promise<void>;
  onUpdateOrg: (
    id: string,
    updates: Partial<OrganizationNode>
  ) => Promise<void>;
  onDeleteOrg: (id: string) => Promise<void>;
}

function Node({
  node,
  style,
  dragHandle,
  onCreateOrg,
  onUpdateOrg,
  onDeleteOrg,
}: OrganizationNodeRendererProps) {
  const [isEditing, setIsEditing] = useState(false);
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
    <div
      className={cn(
        "group flex min-w-0 items-center gap-2 rounded-md px-3 py-2 cursor-pointer transition-colors",
        "hover:bg-background-neutral-02",
        node.isSelected &&
          "bg-background-primary-01 border border-border-primary"
      )}
      style={style}
      ref={dragHandle}
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
          tooltip="Rename"
          tertiary
          small
          aria-label={`Rename ${node.data.name}`}
          onClick={(event) => {
            event.stopPropagation();
            setIsEditing(true);
          }}
        />
        <IconButton
          icon={SvgFolderPlus}
          tooltip="Add child"
          tertiary
          small
          aria-label={`Add child to ${node.data.name}`}
          onClick={(event) => {
            event.stopPropagation();
            void onCreateOrg(node.data.id);
          }}
        />
        <IconButton
          icon={SvgTrash}
          tooltip="Delete"
          danger
          tertiary
          small
          aria-label={`Delete ${node.data.name}`}
          onClick={(event) => {
            event.stopPropagation();
            if (confirm(`Delete "${node.data.name}"?`)) {
              void onDeleteOrg(node.data.id);
            }
          }}
        />
      </div>
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
  selectedOrgId,
  className,
}: OrganizationTreeProps) {
  const [newOrgName, setNewOrgName] = useState("");
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

  const handleCreate = useCallback(
    async (parentId: string | null) => {
      const name = prompt("Enter organization name:");
      if (name && name.trim()) {
        await onCreateOrg(parentId, name.trim());
      }
    },
    [onCreateOrg]
  );

  const handleMove = useCallback(
    async ({
      dragIds,
      parentId,
      parentNode,
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
            Organizations
          </Text>
        </div>

        {organizations.length === 0 && (
          <Button action primary size="md" onClick={() => handleCreate(null)}>
            Add Root Organization
          </Button>
        )}
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
              No organizations yet
            </Text>
            <Text className={cn("text-text-03 text-sm mb-4")}>
              Create your first organization to get started
            </Text>
            <Button action primary size="md" onClick={() => handleCreate(null)}>
              Create Organization
            </Button>
          </div>
        ) : (
          <Tree
            data={organizations}
            openByDefault={false}
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
                onCreateOrg={handleCreate}
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
