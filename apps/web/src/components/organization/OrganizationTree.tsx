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
import {
  Tree,
  NodeRendererProps,
  RowRendererProps,
  type TreeApi,
} from "react-arborist";
import { useTranslation } from "react-i18next";
import { OrganizationSearchCombobox } from "@/components/organization/OrganizationSearchCombobox";
import { LoadingAnimation } from "@/components/Loading";
import type {
  MoveOrganization,
  OrganizationMembersByUnit,
  OrganizationNode,
  OrganizationSearchProps,
} from "@/components/organization/organizationTypes";
import { OrganizationMoveConfirmationModal } from "@/components/organization/OrganizationMoveConfirmationModal";
import {
  organizationMemberDetail,
  organizationMemberInitials,
  organizationMemberName,
} from "@/components/organization/organizationMembers";
import {
  flattenOrganizations,
  organizationMatchesSearch,
} from "@/components/organization/organizationSearch";
import {
  SvgCheck,
  SvgEdit,
  SvgFolderPlus,
  SvgMaximize2,
  SvgTrash,
  SvgUsers,
  SvgX,
} from "@/icons";
import Button from "@/refresh-components/buttons/Button";
import IconButton from "@/refresh-components/buttons/IconButton";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface OrganizationTreeProps extends Partial<OrganizationSearchProps> {
  organizations: OrganizationNode[];
  onCreateOrg: (parentId: string | null, name: string) => Promise<void>;
  onUpdateOrg: (
    id: string,
    updates: Partial<OrganizationNode>
  ) => Promise<void>;
  onDeleteOrg: (id: string) => Promise<void>;
  onMoveOrg: MoveOrganization;
  onSelectOrg: (org: OrganizationNode) => void;
  onOpenDesigner?: () => void;
  selectedOrgId?: string | null;
  showMembers?: boolean;
  membersByOrganizationId?: OrganizationMembersByUnit;
  onShowMembersChange?: (show: boolean) => void;
  membersLoading?: boolean;
  onExpandOrg?: (orgId: string) => void;
  expandingOrganizationIds?: ReadonlySet<string>;
  className?: string;
}

function OrganizationTreeRow<T>({
  node,
  attrs,
  innerRef,
  children,
}: RowRendererProps<T>) {
  return (
    <div
      {...attrs}
      ref={innerRef}
      onFocus={(e) => e.stopPropagation()}
      onClick={node.handleClick}
      style={{
        ...attrs.style,
        minWidth: "100%",
        maxWidth: "100%",
        width: "100%",
        boxSizing: "border-box",
      }}
      className={cn(
        "w-full max-w-full overflow-hidden box-border",
        attrs.className
      )}
    >
      {children}
    </div>
  );
}

interface OrganizationNodeRendererProps
  extends NodeRendererProps<OrganizationNode> {
  onCreateOrg: (parentId: string | null, name: string) => Promise<void>;
  onUpdateOrg: (
    id: string,
    updates: Partial<OrganizationNode>
  ) => Promise<void>;
  onDeleteOrg: (id: string) => Promise<void>;
  selectedOrgId?: string | null;
  searchQuery: string;
  language: string;
  activeSearchMatchId?: string;
  organizations: OrganizationNode[];
  onRequestMove: (
    organization: OrganizationNode,
    parent: OrganizationNode
  ) => void;
  membersByOrganizationId: OrganizationMembersByUnit;
  showMembers: boolean;
  onExpandOrg?: (orgId: string) => void;
  expandingOrganizationIds?: ReadonlySet<string>;
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
  selectedOrgId,
  searchQuery,
  language,
  activeSearchMatchId,
  organizations,
  onRequestMove,
  membersByOrganizationId,
  showMembers,
  onExpandOrg,
  expandingOrganizationIds,
}: OrganizationNodeRendererProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [isCreatingChild, setIsCreatingChild] = useState(false);
  const [editName, setEditName] = useState(node.data.name);
  const inputRef = useRef<HTMLInputElement>(null);
  const isSearchMatch = organizationMatchesSearch(
    node.data,
    searchQuery,
    language
  );
  const hasSearch = Boolean(searchQuery.trim());
  const isExpanding = expandingOrganizationIds?.has(node.data.id) ?? false;
  const directMembers = membersByOrganizationId[node.data.id] ?? [];

  const handleSave = useCallback(() => {
    const trimmed = editName.trim();
    if (trimmed && trimmed !== node.data.name) {
      void onUpdateOrg(node.data.id, { name: trimmed });
    }
    setIsEditing(false);
  }, [editName, node.data.id, node.data.name, onUpdateOrg]);

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

  const isExpandable =
    (node.children !== null &&
      node.children !== undefined &&
      node.children.length > 0) ||
    (node.data.children !== undefined && node.data.children.length > 0) ||
    node.data.has_children === true ||
    (node.data.children_count !== undefined && node.data.children_count > 0);

  const handleToggleNode = useCallback(() => {
    if (isExpandable) {
      const willOpen = !node.isOpen;
      node.toggle();
      if (willOpen && onExpandOrg) {
        onExpandOrg(node.data.id);
      }
    }
  }, [isExpandable, node, onExpandOrg]);

  return (
    <div
      style={{ ...style, boxSizing: "border-box" }}
      ref={dragHandle}
      className="box-border w-full max-w-full min-w-0 overflow-hidden pr-1"
    >
      <div
        data-search-state={
          isSearchMatch ? "match" : hasSearch ? "dimmed" : "idle"
        }
        className={cn(
          "group flex w-full min-w-0 max-w-full items-center gap-2 rounded-md px-2 py-1.5 cursor-pointer transition-[background-color,border-color,box-shadow] duration-200 motion-reduce:transition-none overflow-hidden",
          "hover:bg-background-neutral-02",
          isSearchMatch &&
            "bg-background-neutral-03 ring-1 ring-action-link-05",
          activeSearchMatchId === node.data.id && "ring-2 shadow-md",
          hasSearch && !isSearchMatch && "opacity-30",
          selectedOrgId &&
            node.data.parent_id === selectedOrgId &&
            "bg-background-neutral-02",
          node.isSelected &&
            "bg-background-neutral-02 border border-border-primary"
        )}
        onClick={handleToggleNode}
      >
        {/* Expand/Collapse Icon */}
        {isExpandable ? (
          <div
            className={cn("flex h-4 w-4 shrink-0 items-center justify-center")}
            aria-hidden="true"
          >
            {isExpanding ? (
              <LoadingAnimation text="" size="text-sm" />
            ) : node.isOpen ? (
              "−"
            ) : (
              "+"
            )}
          </div>
        ) : (
          <div className={cn("w-4 shrink-0")} />
        )}

        {/* Name (editable) */}
        {isEditing ? (
          <div
            className={cn("flex min-w-0 flex-1 items-center gap-1")}
            onClick={(event) => event.stopPropagation()}
          >
            <input
              ref={inputRef}
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onKeyDown={handleKeyDown}
              className={cn(
                "min-w-0 flex-1 h-7 rounded-md border border-action-link-05 bg-background-neutral-00 px-2 py-0.5 text-sm text-text-05 focus:outline-none focus:ring-1 focus:ring-action-link-05"
              )}
              autoFocus
            />
            <IconButton
              icon={SvgCheck}
              small
              action
              tooltip={t("admin.organizations.actions.saveChanges")}
              aria-label={t("admin.organizations.actions.saveChanges")}
              disabled={!editName.trim() || editName.trim() === node.data.name}
              onClick={(event) => {
                event.stopPropagation();
                handleSave();
              }}
            />
            <IconButton
              icon={SvgX}
              small
              tertiary
              tooltip={t("admin.organizations.actions.cancel")}
              aria-label={t("admin.organizations.actions.cancel")}
              onClick={(event) => {
                event.stopPropagation();
                setEditName(node.data.name);
                setIsEditing(false);
              }}
            />
          </div>
        ) : (
          <Text
            as="p"
            text05
            title={node.data.name}
            className={cn("min-w-0 flex-1 truncate text-sm font-medium")}
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
                "flex shrink-0 items-center gap-1 px-1.5 py-0.5 rounded bg-background-neutral-02"
              )}
            >
              <Text className={cn("text-xs text-text-03")}>
                {node.data.user_count}
              </Text>
            </div>
          )}

          {node.isSelected && (
            <div
              className={cn("flex shrink-0 items-center gap-0.5")}
              onClick={(event) => event.stopPropagation()}
            >
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
          )}
        </div>
      </div>
      {showMembers && directMembers.length > 0 && (
        <div
          className={cn(
            "ml-9 mr-2 max-h-20 overflow-y-auto border-l-2 border-border-02 pl-2 pt-1"
          )}
        >
          {directMembers.map((member) => (
            <div
              key={member.id}
              data-testid={`organization-member-${member.user_id}`}
              className={cn(
                "mb-1 flex min-w-0 items-center gap-2 rounded-08 bg-background-neutral-02 px-2 py-1"
              )}
              onClick={(event) => event.stopPropagation()}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-background-neutral-04 font-secondary-mono text-[10px] text-text-05"
                )}
              >
                {organizationMemberInitials(member)}
              </span>
              <SvgUsers className={cn("h-3.5 w-3.5 shrink-0 stroke-text-03")} />
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
        </div>
      )}
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
  showMembers = false,
  membersByOrganizationId = {},
  onShowMembersChange,
  membersLoading = false,
  onExpandOrg,
  expandingOrganizationIds,
  className,
  searchResults = [],
  searchLoading = false,
  searchError = null,
  resultsLimited = false,
  revealLoading = false,
  onSearch = () => {},
  onRevealResult = () => {},
  revealRequest = null,
  onRevealReady = onSelectOrg,
}: OrganizationTreeProps) {
  const { t, i18n } = useTranslation();
  const [isCreating, setIsCreating] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSearchMatchIndex, setActiveSearchMatchIndex] = useState(-1);
  const [pendingMove, setPendingMove] = useState<{
    organization: OrganizationNode;
    parent: OrganizationNode;
  } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const treeRef = useRef<TreeApi<OrganizationNode> | null>(null);
  const previousOpenIdsRef = useRef<Set<string> | null>(null);
  const [treeHeight, setTreeHeight] = useState(600);
  const activeSearchMatchId =
    searchResults[activeSearchMatchIndex >= 0 ? activeSearchMatchIndex : 0]?.id;

  useEffect(() => {
    const tree = treeRef.current;
    if (!tree) return;
    if (searchQuery.trim()) {
      if (!previousOpenIdsRef.current) {
        previousOpenIdsRef.current = new Set(
          flattenOrganizations(organizations)
            .filter((organization) => tree.isOpen(organization.id))
            .map((organization) => organization.id)
        );
      }
      tree.openAll();
    } else if (previousOpenIdsRef.current) {
      tree.closeAll();
      previousOpenIdsRef.current.forEach((id) => tree.open(id));
      previousOpenIdsRef.current = null;
    }
  }, [organizations, searchQuery]);

  const completedRevealIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (!revealRequest || completedRevealIdRef.current === revealRequest.id) {
      return;
    }
    const organization = flattenOrganizations(organizations).find(
      ({ id }) => id === revealRequest.result.id
    );
    if (!organization) return;
    revealRequest.ancestorIds.forEach((id) => treeRef.current?.open(id));
    completedRevealIdRef.current = revealRequest.id;
    onRevealReady(organization);
    window.requestAnimationFrame(() => {
      void treeRef.current?.scrollTo(organization.id, "center");
      treeRef.current?.focus(organization.id);
    });
  }, [onRevealReady, organizations, revealRequest]);

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

      const organization = flattenOrganizations(organizations).find(
        (item) => item.id === dragIds[0]
      );
      const parent = flattenOrganizations(organizations).find(
        (item) => item.id === parentId
      );
      if (organization && parent && organization.parent_id !== parent.id)
        setPendingMove({ organization, parent });
    },
    [organizations]
  );

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Header */}
      <div className={cn("border-b border-border-02 p-4")}>
        <div className={cn("flex items-center justify-between gap-2")}>
          <Text className={cn("text-lg font-semibold text-text-05")}>
            {t("admin.organizations.tree.title")}
          </Text>
          <div className={cn("flex items-center gap-1")}>
            {onShowMembersChange && (
              <Button
                aria-pressed={showMembers}
                disabled={membersLoading}
                secondary
                size="md"
                onClick={() => onShowMembersChange(!showMembers)}
              >
                {t(
                  membersLoading
                    ? "admin.organizations.tree.loadingMembers"
                    : showMembers
                      ? "admin.organizations.tree.hideMembers"
                      : "admin.organizations.tree.showMembers"
                )}
              </Button>
            )}
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
        <OrganizationSearchCombobox
          className={cn("mt-3")}
          query={searchQuery}
          activeIndex={activeSearchMatchIndex}
          results={searchResults}
          loading={searchLoading}
          error={searchError}
          limited={resultsLimited}
          revealLoading={revealLoading}
          onQueryChange={setSearchQuery}
          onActiveIndexChange={setActiveSearchMatchIndex}
          onSearch={onSearch}
          onReveal={onRevealResult}
        />
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
            ref={treeRef}
            data={organizations}
            renderRow={OrganizationTreeRow}
            openByDefault={false}
            initialOpenState={Object.fromEntries(
              organizations.map((organization) => [organization.id, true])
            )}
            width="100%"
            height={treeHeight}
            indent={20}
            rowHeight={(node) =>
              showMembers &&
              (membersByOrganizationId[node.data.id]?.length ?? 0) > 0
                ? 136
                : 40
            }
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
                selectedOrgId={selectedOrgId}
                searchQuery={searchQuery}
                language={i18n.language}
                activeSearchMatchId={activeSearchMatchId}
                organizations={flattenOrganizations(organizations)}
                onRequestMove={(organization, parent) =>
                  setPendingMove({ organization, parent })
                }
                showMembers={showMembers}
                membersByOrganizationId={membersByOrganizationId}
                expandingOrganizationIds={expandingOrganizationIds}
                onExpandOrg={onExpandOrg}
              />
            )}
          </Tree>
        )}
      </div>
      {pendingMove && (
        <OrganizationMoveConfirmationModal
          organizationName={pendingMove.organization.name}
          currentParentName={
            flattenOrganizations(organizations).find(
              (item) => item.id === pendingMove.organization.parent_id
            )?.name ?? t("admin.organizations.moveConfirm.noParent")
          }
          newParentName={pendingMove.parent.name}
          onCancel={() => setPendingMove(null)}
          onConfirm={() => {
            void onMoveOrg(pendingMove.organization.id, pendingMove.parent.id);
            setPendingMove(null);
          }}
        />
      )}
    </div>
  );
}
