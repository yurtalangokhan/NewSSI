"use client";

import React, { useState, useMemo, memo, useCallback, useEffect } from "react";
import * as GeneralLayouts from "@/layouts/general-layouts";
import { Content } from "@opal/layouts";
import * as TableLayouts from "@/layouts/table-layouts";
import * as InputLayouts from "@/layouts/input-layouts";
import { Card } from "@/refresh-components/cards";
import Button from "@/refresh-components/buttons/Button";
import { Button as OpalButton } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import LineItem from "@/refresh-components/buttons/LineItem";
import Separator from "@/refresh-components/Separator";
import Switch from "@/refresh-components/inputs/Switch";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import Spacer from "@/refresh-components/Spacer";
import { Disabled } from "@/refresh-components/Disabled";
import {
  SvgPlusCircle,
  SvgArrowUpRight,
  SvgFiles,
  SvgNetworkGraph,
} from "@opal/icons";
import {
  useKnowledgeCollections,
  type KnowledgeCollection,
} from "@/hooks/useKnowledgeCollections";
import { useTranslation } from "react-i18next";

// Knowledge pane view states
type KnowledgeView = "main" | "add" | "document-processing" | "knowledge-graph";

export interface AgentKnowledgePaneProps {
  enableKnowledge: boolean;
  onEnableKnowledgeChange: (enabled: boolean) => void;
  ragDocumentCollectionIds: string[];
  onDocumentCollectionIdsChange: (ids: string[]) => void;
  ragGraphCollectionIds: string[];
  onGraphCollectionIdsChange: (ids: string[]) => void;
}

// ============================================================================
// SYNC STATUS DOT
// ============================================================================

function SyncStatusDot({ status }: { status: string }) {
  const color =
    status === "idle"
      ? "bg-green-500"
      : status === "syncing" || status === "starting"
      ? "bg-yellow-500"
      : status === "error"
      ? "bg-red-500"
      : "bg-gray-400";

  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${color}`}
      title={status}
    />
  );
}

// ============================================================================
// KNOWLEDGE SIDEBAR
// ============================================================================

interface KnowledgeSidebarProps {
  activeView: KnowledgeView;
  selectedDocumentCollectionIds: string[];
  selectedGraphCollectionIds: string[];
  onNavigateToDocumentProcessing: () => void;
  onNavigateToKnowledgeGraph: () => void;
}

function KnowledgeSidebar({
  activeView,
  selectedDocumentCollectionIds,
  selectedGraphCollectionIds,
  onNavigateToDocumentProcessing,
  onNavigateToKnowledgeGraph,
}: KnowledgeSidebarProps) {
  const { t } = useTranslation();
  return (
    <TableLayouts.SidebarLayout aria-label="knowledge-sidebar">
      <LineItem
        icon={SvgFiles}
        onClick={onNavigateToDocumentProcessing}
        selected={activeView === "document-processing"}
        emphasized={
          activeView === "document-processing" ||
          selectedDocumentCollectionIds.length > 0
        }
        aria-label="knowledge-sidebar-document-processing"
        rightChildren={
          selectedDocumentCollectionIds.length > 0 ? (
            <Text mainUiAction className="text-action-link-05">
              {selectedDocumentCollectionIds.length}
            </Text>
          ) : undefined
        }
      >
        {t("agentKnowledge.documentProcessing")}
      </LineItem>

      <LineItem
        icon={SvgNetworkGraph}
        onClick={onNavigateToKnowledgeGraph}
        selected={activeView === "knowledge-graph"}
        emphasized={
          activeView === "knowledge-graph" ||
          selectedGraphCollectionIds.length > 0
        }
        aria-label="knowledge-sidebar-knowledge-graph"
        rightChildren={
          selectedGraphCollectionIds.length > 0 ? (
            <Text mainUiAction className="text-action-link-05">
              {selectedGraphCollectionIds.length}
            </Text>
          ) : undefined
        }
      >
        {t("agentKnowledge.knowledgeGraph")}
      </LineItem>
    </TableLayouts.SidebarLayout>
  );
}

// ============================================================================
// KNOWLEDGE TABLE - Generic table for collection items
// ============================================================================

interface KnowledgeTableColumn<T> {
  key: string;
  header: string;
  width?: number;
  render: (item: T) => React.ReactNode;
}

interface KnowledgeTableProps<T> {
  items: T[];
  columns: KnowledgeTableColumn<T>[];
  getItemId: (item: T) => string;
  selectedIds: string[];
  onToggleItem: (id: string) => void;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  searchPlaceholder?: string;
  emptyMessage?: string;
  isLoading?: boolean;
  ariaLabelPrefix?: string;
}

function KnowledgeTable<T>({
  items,
  columns,
  getItemId,
  selectedIds,
  onToggleItem,
  searchValue,
  onSearchChange,
  searchPlaceholder,
  emptyMessage,
  isLoading,
  ariaLabelPrefix,
}: KnowledgeTableProps<T>) {
  const { t } = useTranslation();
  const resolvedSearchPlaceholder = searchPlaceholder ?? t("agentKnowledge.searchPlaceholder");
  const resolvedEmptyMessage = emptyMessage ?? t("agentKnowledge.noItemsAvailable");
  if (isLoading) {
    return (
      <GeneralLayouts.Section height="auto" padding={1}>
        <SimpleLoader />
      </GeneralLayouts.Section>
    );
  }

  return (
    <GeneralLayouts.Section gap={0} alignItems="stretch" justifyContent="start">
      {onSearchChange !== undefined && (
        <GeneralLayouts.Section height="auto">
          <InputTypeIn
            leftSearchIcon
            value={searchValue ?? ""}
            onChange={(e) => onSearchChange?.(e.target.value)}
            placeholder={resolvedSearchPlaceholder}
            variant="internal"
          />
        </GeneralLayouts.Section>
      )}

      <Spacer rem={0.5} />

      {/* Table header */}
      <TableLayouts.TableRow>
        <TableLayouts.CheckboxCell />
        {columns.map((column) => (
          <TableLayouts.TableCell
            key={column.key}
            flex={!column.width}
            width={column.width}
          >
            <GeneralLayouts.Section
              flexDirection="row"
              justifyContent="start"
              alignItems="center"
              gap={0.25}
              height="auto"
            >
              <Text secondaryBody text03>
                {column.header}
              </Text>
            </GeneralLayouts.Section>
          </TableLayouts.TableCell>
        ))}
      </TableLayouts.TableRow>

      <Separator noPadding />

      {/* Table body */}
      {items.length === 0 ? (
        <GeneralLayouts.Section height="auto" padding={1}>
          <Text text03 secondaryBody>
            {resolvedEmptyMessage}
          </Text>
        </GeneralLayouts.Section>
      ) : (
        <GeneralLayouts.Section gap={0} alignItems="stretch" height="auto">
          {items.map((item) => {
            const id = getItemId(item);
            const isSelected = selectedIds.includes(id);

            return (
              <TableLayouts.TableRow
                key={id}
                selected={isSelected}
                onClick={() => onToggleItem(id)}
                aria-label={
                  ariaLabelPrefix ? `${ariaLabelPrefix}-${id}` : undefined
                }
              >
                <TableLayouts.CheckboxCell>
                  <Checkbox
                    checked={isSelected}
                    onCheckedChange={() => onToggleItem(id)}
                  />
                </TableLayouts.CheckboxCell>
                {columns.map((column) => (
                  <TableLayouts.TableCell
                    key={column.key}
                    flex={!column.width}
                    width={column.width}
                  >
                    {column.render(item)}
                  </TableLayouts.TableCell>
                ))}
              </TableLayouts.TableRow>
            );
          })}
        </GeneralLayouts.Section>
      )}
    </GeneralLayouts.Section>
  );
}

// ============================================================================
// COLLECTION TABLE CONTENT - Table for document processing / knowledge graph
// ============================================================================

interface CollectionTableContentProps {
  collections: KnowledgeCollection[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  isLoading: boolean;
  emptyMessage: string;
  ariaLabelPrefix: string;
}

function CollectionTableContent({
  collections,
  selectedIds,
  onToggle,
  isLoading,
  emptyMessage,
  ariaLabelPrefix,
}: CollectionTableContentProps) {
  const { t } = useTranslation();
  const [searchValue, setSearchValue] = useState("");

  const filteredCollections = useMemo(() => {
    if (!searchValue) return collections;
    const lower = searchValue.toLowerCase();
    return collections.filter((c) => c.name.toLowerCase().includes(lower));
  }, [collections, searchValue]);

  const columns: KnowledgeTableColumn<KnowledgeCollection>[] = [
    {
      key: "name",
      header: t("agentKnowledge.columnName"),
      render: (col) => (
        <div className="flex items-center gap-2 min-w-0">
          <Text className="truncate">{col.name}</Text>
          {col.connector_type && (
            <span className="shrink-0 rounded bg-background-300 px-1.5 py-0.5 text-xs text-text-500">
              {col.connector_type.replace("source-", "")}
            </span>
          )}
        </div>
      ),
    },
    {
      key: "status",
      header: t("agentKnowledge.columnStatus"),
      width: 6,
      render: (col) => (
        <div className="flex items-center gap-1.5">
          <SyncStatusDot status={col.sync_status} />
          <Text text03 secondaryBody>
            {col.sync_status}
          </Text>
        </div>
      ),
    },
  ];

  return (
    <KnowledgeTable
      items={filteredCollections}
      columns={columns}
      getItemId={(col) => col.id}
      selectedIds={selectedIds}
      onToggleItem={onToggle}
      searchValue={searchValue}
      onSearchChange={setSearchValue}
      searchPlaceholder={t("agentKnowledge.searchCollections")}
      emptyMessage={emptyMessage}
      isLoading={isLoading}
      ariaLabelPrefix={ariaLabelPrefix}
    />
  );
}

// ============================================================================
// TWO-COLUMN LAYOUT - Sidebar + Table
// ============================================================================

interface KnowledgeTwoColumnViewProps {
  activeView: KnowledgeView;
  selectedDocumentCollectionIds: string[];
  selectedGraphCollectionIds: string[];
  documentProcessingCollections: KnowledgeCollection[];
  knowledgeGraphCollections: KnowledgeCollection[];
  isLoading: boolean;
  onNavigateToDocumentProcessing: () => void;
  onNavigateToKnowledgeGraph: () => void;
  onDocumentCollectionToggle: (id: string) => void;
  onGraphCollectionToggle: (id: string) => void;
}

const KnowledgeTwoColumnView = memo(function KnowledgeTwoColumnView({
  activeView,
  selectedDocumentCollectionIds,
  selectedGraphCollectionIds,
  documentProcessingCollections,
  knowledgeGraphCollections,
  isLoading,
  onNavigateToDocumentProcessing,
  onNavigateToKnowledgeGraph,
  onDocumentCollectionToggle,
  onGraphCollectionToggle,
}: KnowledgeTwoColumnViewProps) {
  const { t } = useTranslation();
  return (
    <TableLayouts.TwoColumnLayout minHeight={18.75}>
      <KnowledgeSidebar
        activeView={activeView}
        selectedDocumentCollectionIds={selectedDocumentCollectionIds}
        selectedGraphCollectionIds={selectedGraphCollectionIds}
        onNavigateToDocumentProcessing={onNavigateToDocumentProcessing}
        onNavigateToKnowledgeGraph={onNavigateToKnowledgeGraph}
      />

      <TableLayouts.ContentColumn>
        {activeView === "document-processing" && (
          <CollectionTableContent
            collections={documentProcessingCollections}
            selectedIds={selectedDocumentCollectionIds}
            onToggle={onDocumentCollectionToggle}
            isLoading={isLoading}
            emptyMessage={t("agentKnowledge.noDatasourcesFound")}
            ariaLabelPrefix="doc-collection-row"
          />
        )}
        {activeView === "knowledge-graph" && (
          <CollectionTableContent
            collections={knowledgeGraphCollections}
            selectedIds={selectedGraphCollectionIds}
            onToggle={onGraphCollectionToggle}
            isLoading={isLoading}
            emptyMessage={t("agentKnowledge.noKnowledgeGraphCollections")}
            ariaLabelPrefix="graph-collection-row"
          />
        )}
      </TableLayouts.ContentColumn>
    </TableLayouts.TwoColumnLayout>
  );
});

// ============================================================================
// KNOWLEDGE ADD VIEW - Pill selection view
// ============================================================================

interface KnowledgeAddViewProps {
  onNavigateToDocumentProcessing: () => void;
  onNavigateToKnowledgeGraph: () => void;
  selectedDocumentCollectionIds: string[];
  selectedGraphCollectionIds: string[];
}

const KnowledgeAddView = memo(function KnowledgeAddView({
  onNavigateToDocumentProcessing,
  onNavigateToKnowledgeGraph,
  selectedDocumentCollectionIds,
  selectedGraphCollectionIds,
}: KnowledgeAddViewProps) {
  const { t } = useTranslation();
  return (
    <GeneralLayouts.Section
      gap={0.5}
      alignItems="start"
      height="auto"
      aria-label="knowledge-add-view"
    >
      <GeneralLayouts.Section
        flexDirection="row"
        justifyContent="start"
        gap={0.5}
        height="auto"
        wrap
      >
        <LineItem
          icon={SvgFiles}
          description={t("agentKnowledge.vectorSimilaritySearch")}
          onClick={onNavigateToDocumentProcessing}
          emphasized={selectedDocumentCollectionIds.length > 0}
          aria-label="knowledge-add-document-processing"
          rightChildren={
            selectedDocumentCollectionIds.length > 0 ? (
              <Text mainUiAction className="text-action-link-05">
                {selectedDocumentCollectionIds.length}
              </Text>
            ) : undefined
          }
        >
          {t("agentKnowledge.documentProcessing")}
        </LineItem>

        <LineItem
          icon={SvgNetworkGraph}
          description={t("agentKnowledge.neo4jHybridSearch")}
          onClick={onNavigateToKnowledgeGraph}
          emphasized={selectedGraphCollectionIds.length > 0}
          aria-label="knowledge-add-knowledge-graph"
          rightChildren={
            selectedGraphCollectionIds.length > 0 ? (
              <Text mainUiAction className="text-action-link-05">
                {selectedGraphCollectionIds.length}
              </Text>
            ) : undefined
          }
        >
          {t("agentKnowledge.knowledgeGraph")}
        </LineItem>
      </GeneralLayouts.Section>
    </GeneralLayouts.Section>
  );
});

// ============================================================================
// KNOWLEDGE MAIN CONTENT - Empty state and preview
// ============================================================================

interface KnowledgeMainContentProps {
  hasAnyKnowledge: boolean;
  totalSelected: number;
  onAddKnowledge: () => void;
  onViewEdit: () => void;
}

const KnowledgeMainContent = memo(function KnowledgeMainContent({
  hasAnyKnowledge,
  totalSelected,
  onAddKnowledge,
  onViewEdit,
}: KnowledgeMainContentProps) {
  const { t } = useTranslation();
  if (!hasAnyKnowledge) {
    return (
      <GeneralLayouts.Section
        flexDirection="row"
        justifyContent="between"
        alignItems="center"
        height="auto"
      >
        <Text text03 secondaryBody>
          {t("agentKnowledge.addKnowledgeDescription")}
        </Text>
        <OpalButton
          icon={SvgPlusCircle}
          onClick={onAddKnowledge}
          prominence="tertiary"
          aria-label="knowledge-add-button"
        />
      </GeneralLayouts.Section>
    );
  }

  return (
    <GeneralLayouts.Section
      flexDirection="row"
      justifyContent="between"
      alignItems="center"
      height="auto"
    >
      <Text as="p" text03 secondaryBody>
        {t("agentKnowledge.knowledgeSourcesSelected", { count: totalSelected })}
      </Text>
      <Button
        internal
        leftIcon={SvgArrowUpRight}
        onClick={onViewEdit}
        aria-label="knowledge-view-edit"
      >
        {t("agentKnowledge.viewEdit")}
      </Button>
    </GeneralLayouts.Section>
  );
});

// ============================================================================
// MAIN COMPONENT - AgentKnowledgePane
// ============================================================================

export default function AgentKnowledgePane({
  enableKnowledge,
  onEnableKnowledgeChange,
  ragDocumentCollectionIds,
  onDocumentCollectionIdsChange,
  ragGraphCollectionIds,
  onGraphCollectionIdsChange,
}: AgentKnowledgePaneProps) {
  const { t } = useTranslation();
  const [view, setView] = useState<KnowledgeView>("main");
  const { collections, isLoading } = useKnowledgeCollections(enableKnowledge);

  // Reset view when knowledge is disabled
  useEffect(() => {
    if (!enableKnowledge) {
      setView("main");
    }
  }, [enableKnowledge]);

  const hasAnyKnowledge =
    ragDocumentCollectionIds.length > 0 || ragGraphCollectionIds.length > 0;

  const totalSelected =
    ragDocumentCollectionIds.length + ragGraphCollectionIds.length;

  // Navigation handlers
  const handleNavigateToAdd = useCallback(() => setView("add"), []);
  const handleNavigateToDocumentProcessing = useCallback(
    () => setView("document-processing"),
    []
  );
  const handleNavigateToKnowledgeGraph = useCallback(
    () => setView("knowledge-graph"),
    []
  );

  // Toggle handlers
  const handleDocumentCollectionToggle = useCallback(
    (id: string) => {
      const newIds = ragDocumentCollectionIds.includes(id)
        ? ragDocumentCollectionIds.filter((x) => x !== id)
        : [...ragDocumentCollectionIds, id];
      onDocumentCollectionIdsChange(newIds);
    },
    [ragDocumentCollectionIds, onDocumentCollectionIdsChange]
  );

  const handleGraphCollectionToggle = useCallback(
    (id: string) => {
      const newIds = ragGraphCollectionIds.includes(id)
        ? ragGraphCollectionIds.filter((x) => x !== id)
        : [...ragGraphCollectionIds, id];
      onGraphCollectionIdsChange(newIds);
    },
    [ragGraphCollectionIds, onGraphCollectionIdsChange]
  );

  // Rendered content based on view
  const renderedContent = useMemo(() => {
    switch (view) {
      case "main":
        return (
          <KnowledgeMainContent
            hasAnyKnowledge={hasAnyKnowledge}
            totalSelected={totalSelected}
            onAddKnowledge={handleNavigateToAdd}
            onViewEdit={handleNavigateToAdd}
          />
        );

      case "add":
        return (
          <KnowledgeAddView
            onNavigateToDocumentProcessing={handleNavigateToDocumentProcessing}
            onNavigateToKnowledgeGraph={handleNavigateToKnowledgeGraph}
            selectedDocumentCollectionIds={ragDocumentCollectionIds}
            selectedGraphCollectionIds={ragGraphCollectionIds}
          />
        );

      case "document-processing":
      case "knowledge-graph":
        return (
          <KnowledgeTwoColumnView
            activeView={view}
            selectedDocumentCollectionIds={ragDocumentCollectionIds}
            selectedGraphCollectionIds={ragGraphCollectionIds}
            documentProcessingCollections={
              collections?.document_processing ?? []
            }
            knowledgeGraphCollections={collections?.knowledge_graph ?? []}
            isLoading={isLoading}
            onNavigateToDocumentProcessing={handleNavigateToDocumentProcessing}
            onNavigateToKnowledgeGraph={handleNavigateToKnowledgeGraph}
            onDocumentCollectionToggle={handleDocumentCollectionToggle}
            onGraphCollectionToggle={handleGraphCollectionToggle}
          />
        );

      default:
        return null;
    }
  }, [
    view,
    hasAnyKnowledge,
    totalSelected,
    ragDocumentCollectionIds,
    ragGraphCollectionIds,
    collections,
    isLoading,
    handleNavigateToAdd,
    handleNavigateToDocumentProcessing,
    handleNavigateToKnowledgeGraph,
    handleDocumentCollectionToggle,
    handleGraphCollectionToggle,
  ]);

  return (
    <GeneralLayouts.Section gap={0.5} alignItems="stretch" height="auto">
      <Content
        title={t("agentKnowledge.title")}
        description={t("agentKnowledge.description")}
        sizePreset="main-content"
        variant="section"
      />

      <Card>
        <GeneralLayouts.Section gap={0.5} alignItems="stretch" height="auto">
          <InputLayouts.Horizontal
            title={t("agentKnowledge.useKnowledge")}
            description={t("agentKnowledge.useKnowledgeDescription")}
          >
            <Switch
              name="enable_knowledge"
              checked={enableKnowledge}
              onCheckedChange={onEnableKnowledgeChange}
            />
          </InputLayouts.Horizontal>

          <Disabled disabled={!enableKnowledge}>
            <GeneralLayouts.Section alignItems="stretch" height="auto">
              {renderedContent}
            </GeneralLayouts.Section>
          </Disabled>
        </GeneralLayouts.Section>
      </Card>
    </GeneralLayouts.Section>
  );
}
