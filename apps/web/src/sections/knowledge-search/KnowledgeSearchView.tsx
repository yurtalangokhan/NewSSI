"use client";

import DocumentPreview from "@/sections/knowledge-search/components/DocumentPreview";
import EntityPreview from "@/sections/knowledge-search/components/EntityPreview";
import GraphCanvas from "@/sections/knowledge-search/components/GraphCanvas";
import ResultList from "@/sections/knowledge-search/components/ResultList";
import ResultTabs from "@/sections/knowledge-search/components/ResultTabs";
import SearchBox from "@/sections/knowledge-search/components/SearchBox";
import SearchFilterBar from "@/sections/knowledge-search/components/SearchFilterBar";
import SearchLanding from "@/sections/knowledge-search/components/SearchLanding";
import SearchPreviewDrawer from "@/sections/knowledge-search/components/SearchPreviewDrawer";
import SearchSummaryRail from "@/sections/knowledge-search/components/SearchSummaryRail";
import SearchSummaryRailSkeleton from "@/sections/knowledge-search/components/SearchSummaryRailSkeleton";
import { useKnowledgeSearchController } from "@/sections/knowledge-search/state/useKnowledgeSearchController";

/**
 * The knowledge search page: one query over document passages and the
 * knowledge graph of every collection the user can read.
 */
export default function KnowledgeSearchView() {
  const search = useKnowledgeSearchController();
  const { state, result, selected } = search;

  if (state.query === null) {
    return (
      <SearchLanding
        draft={state.draft}
        kind={state.kind}
        onDraftChange={search.setDraft}
        onSubmit={search.submit}
        onClear={search.clear}
        onKindChange={search.setKind}
        graphDisabled={!search.canSearchGraph}
        sources={search.sources}
        sourcesLoading={search.sourcesLoading}
        sourcesError={search.sourcesError}
        selectedCollectionIds={state.collectionIds}
        onCollectionToggle={search.toggleCollection}
        recentSearches={search.recentSearches}
        onRecentSelect={search.applyQuery}
        onClearRecent={search.clearRecentSearches}
      />
    );
  }

  return (
    <div className="flex w-full flex-col items-center px-6 pb-10 pt-6 animate-in fade-in slide-in-from-bottom-1 duration-200 motion-reduce:animate-none">
      <div className="w-full max-w-[78rem] rounded-16 border border-border-01 bg-background-tint-00 p-5 shadow-01">
        <div className="grid min-w-0 grid-cols-1 gap-x-8 gap-y-4 xl:grid-cols-[minmax(0,1fr)_18.75rem]">
          <div className="flex min-w-0 flex-col gap-3.5 xl:col-span-2">
            <SearchBox
              value={state.draft}
              kind={state.kind}
              onChange={search.setDraft}
              onSubmit={search.submit}
              onClear={search.clear}
              onKindChange={search.setKind}
              graphDisabled={!search.canSearchGraph}
              busy={search.isSearching}
              shortcut
            />
            <SearchFilterBar
              sources={search.sources}
              collectionIds={state.collectionIds}
              onCollectionToggle={search.toggleCollection}
              onCollectionsClear={() => search.setCollections([])}
              fileTypes={result?.facets.fileTypes ?? []}
              selectedFileTypes={state.fileTypes}
              onFileTypeToggle={search.toggleFileType}
              onFileTypesClear={search.clearFileTypes}
              entityLabels={result?.facets.entityLabels ?? []}
              selectedEntityLabels={state.entityLabels}
              onEntityLabelToggle={search.toggleEntityLabel}
              onEntityLabelsClear={search.clearEntityLabels}
              limit={state.chosenLimit}
              onLimitChange={search.setLimit}
              isSearching={result !== undefined && search.isSearching}
              total={result?.total}
              elapsedMs={result?.elapsedMs}
            />
          </div>

          <div
            className="min-w-0"
            aria-busy={search.isSearching}
            data-testid="knowledge-search-results"
          >
            <ResultTabs
              tab={state.tab}
              onTabChange={search.setTab}
              resultCount={result?.total ?? 0}
              nodeCount={search.graph.nodes.length}
              listPanel={
                <ResultList
                  response={result}
                  error={search.error}
                  isLoading={search.isLoading}
                  isSearching={search.isSearching}
                  query={state.query}
                  visibleCount={state.visibleCount}
                  limit={state.limit}
                  selectedHitId={search.selectedHitId}
                  hasFilters={search.hasFilters}
                  onOpen={search.openHit}
                  onShowMore={search.showMore}
                  onRetry={search.retry}
                  onResetFilters={search.resetFilters}
                />
              }
              graphPanel={
                <GraphCanvas
                  graph={search.graph}
                  selectedNodeId={
                    selected?.kind === "entity" ? selected.node.id : null
                  }
                  onSelectNode={search.selectNode}
                  depth={state.graphDepth}
                  onDepthChange={search.setDepth}
                  matchedOnly={state.matchedOnly}
                  onMatchedOnlyToggle={search.toggleMatchedOnly}
                  isExpanding={search.isExpanding}
                  canExpand={search.canExpandGraph}
                />
              }
            />
          </div>
          {result ? (
            <SearchSummaryRail
              response={result}
              sources={search.sources}
              graph={search.graph}
              collectionIds={state.collectionIds}
              onCollectionsChange={search.setCollections}
              selectedEntityLabels={state.entityLabels}
              onEntityLabelToggle={search.toggleEntityLabel}
              onOpenGraph={() => search.setTab("graph")}
            />
          ) : search.isSearching ? (
            <SearchSummaryRailSkeleton />
          ) : (
            <div aria-hidden className="hidden xl:block" />
          )}
        </div>
      </div>

      <SearchPreviewDrawer
        open={selected !== null}
        onClose={search.closePreview}
      >
        {selected?.kind === "document" && (
          <DocumentPreview
            hit={selected.hit}
            query={state.query}
            onClose={search.closePreview}
          />
        )}
        {selected?.kind === "entity" && (
          <EntityPreview
            node={selected.node}
            hit={selected.hit}
            graph={search.graph}
            collectionName={selected.collectionName}
            onExpand={search.expandNode}
            isExpanding={search.expandingNodeId === selected.node.id}
            expansionDepth={search.expansionDepthOf(selected.node.id)}
            canExpand={search.canExpandGraph}
            onSelectNode={search.selectNode}
            onClose={search.closePreview}
          />
        )}
      </SearchPreviewDrawer>
    </div>
  );
}
