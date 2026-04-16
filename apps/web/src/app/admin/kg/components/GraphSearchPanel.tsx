"use client";

import { useState } from "react";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import {
  searchGraph,
  type GraphSearchResult,
  type GraphSearchInput,
  type SearchType,
} from "@/lib/langconnect";
import { toast } from "@/hooks/useToast";
import { SvgSearch } from "@opal/icons";
import { cn } from "@/lib/utils";
import { ThreeDotsLoader } from "@/components/Loading";

const SEARCH_TYPES: {
  value: SearchType;
  label: string;
  description: string;
}[] = [
  {
    value: "entity",
    label: "Entity",
    description: "Search by entity similarity",
  },
  {
    value: "cypher",
    label: "Cypher",
    description: "Graph traversal query",
  },
  {
    value: "hybrid",
    label: "Hybrid",
    description: "Combined vector + graph",
  },
];

interface GraphSearchPanelProps {
  collectionId: string | null;
}

export default function GraphSearchPanel({
  collectionId,
}: GraphSearchPanelProps) {
  const [query, setQuery] = useState("");
  const [searchType, setSearchType] = useState<SearchType>("hybrid");
  const [limit, setLimit] = useState(10);
  const [vectorWeight, setVectorWeight] = useState(0.5);
  const [graphWeight, setGraphWeight] = useState(0.5);
  const [isSearching, setIsSearching] = useState(false);
  const [result, setResult] = useState<GraphSearchResult | null>(null);

  const handleSearch = async () => {
    if (!collectionId || !query.trim()) return;
    setIsSearching(true);
    setResult(null);
    try {
      const input: GraphSearchInput = {
        query,
        collection_id: collectionId,
        limit,
        search_type: searchType,
        ...(searchType === "hybrid" && {
          vector_weight: vectorWeight,
          graph_weight: graphWeight,
        }),
      };
      const res = await searchGraph(input);
      setResult(res);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Graph search failed");
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <CardSection className="flex flex-col gap-4">
      <Text as="p" headingH3 text05>
        Graph Search
      </Text>
      <Text as="p" mainContentBody text04 className="leading-relaxed">
        Query the knowledge graph using entity similarity, Cypher graph
        traversal, or a hybrid approach combining both.
      </Text>

      {/* Search type selector */}
      <div className="flex flex-col gap-2">
        <Text
          as="p"
          mainContentMuted
          text03
          className="text-xs font-medium uppercase tracking-wide"
        >
          Search Type
        </Text>
        <div className="grid grid-cols-3 gap-2">
          {SEARCH_TYPES.map(({ value, label, description }) => (
            <button
              key={value}
              onClick={() => setSearchType(value)}
              className={cn(
                "flex flex-col gap-0.5 rounded-08 border px-3 py-2 text-left transition-colors",
                searchType === value
                  ? "border-theme-primary-04 bg-theme-primary-01"
                  : "border-border-01 bg-background-tint-00 hover:bg-background-neutral-01"
              )}
            >
              <Text as="span" mainUiAction text04 className="text-sm font-medium">
                {label}
              </Text>
              <Text as="span" mainContentMuted text03 className="text-xs">
                {description}
              </Text>
            </button>
          ))}
        </div>
      </div>

      {/* Hybrid weights */}
      {searchType === "hybrid" && (
        <div className="flex flex-col gap-3 rounded-08 border border-border-01 bg-background-neutral-01 p-3">
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <Text as="p" mainContentMuted text03 className="text-xs">
                Vector Weight
              </Text>
              <Text
                as="p"
                mainUiAction
                text04
                className="text-xs font-semibold tabular-nums"
              >
                {vectorWeight.toFixed(2)}
              </Text>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={vectorWeight}
              onChange={(e) => setVectorWeight(parseFloat(e.target.value))}
              className="w-full accent-theme-primary-04"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <Text as="p" mainContentMuted text03 className="text-xs">
                Graph Weight
              </Text>
              <Text
                as="p"
                mainUiAction
                text04
                className="text-xs font-semibold tabular-nums"
              >
                {graphWeight.toFixed(2)}
              </Text>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={graphWeight}
              onChange={(e) => setGraphWeight(parseFloat(e.target.value))}
              className="w-full accent-theme-primary-04"
            />
          </div>
        </div>
      )}

      {/* Query row */}
      <div className="flex gap-2 items-center flex-wrap">
        <div className="flex-1 min-w-[200px]">
          <InputTypeIn
            placeholder="Enter your search query..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Text as="span" mainContentMuted text03 className="text-xs whitespace-nowrap">
            Limit
          </Text>
          <input
            type="number"
            min={1}
            max={50}
            value={limit}
            onChange={(e) =>
              setLimit(Math.max(1, parseInt(e.target.value) || 10))
            }
            className="w-16 rounded-08 border border-border-01 bg-background-tint-00 px-2 py-2 text-sm text-text-04 focus:outline-none focus:ring-1 focus:ring-theme-primary-04"
          />
        </div>
        <Button
          leftIcon={SvgSearch}
          onClick={handleSearch}
          disabled={!collectionId || !query.trim() || isSearching}
        >
          Search
        </Button>
      </div>

      {/* Loading */}
      {isSearching && (
        <div className="flex justify-center py-4">
          <ThreeDotsLoader />
        </div>
      )}

      {/* Results */}
      {result && !isSearching && (
        <div className="flex flex-col gap-3">
          {/* Context */}
          {result.context && (
            <div className="rounded-08 border border-border-01 bg-background-neutral-01 p-3">
              <Text
                as="p"
                mainContentMuted
                text03
                className="text-xs font-medium mb-2 uppercase tracking-wide"
              >
                Context
              </Text>
              <Text
                as="p"
                mainContentBody
                text04
                className="text-sm whitespace-pre-wrap leading-relaxed"
              >
                {result.context}
              </Text>
            </div>
          )}

          {/* Nodes */}
          {result.nodes.length > 0 && (
            <div className="flex flex-col gap-2">
              <Text
                as="p"
                mainContentMuted
                text03
                className="text-xs font-medium uppercase tracking-wide"
              >
                Nodes ({result.nodes.length})
              </Text>
              <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto pr-1">
                {result.nodes.map((node) => (
                  <div
                    key={node.id}
                    className="flex items-center gap-2 rounded-08 border border-border-01 bg-background-tint-00 px-3 py-2"
                  >
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full bg-theme-primary-01 border border-theme-primary-03 text-xs text-theme-primary-07 font-medium shrink-0">
                      {node.label}
                    </span>
                    <Text as="p" mainUiAction text04 className="text-sm">
                      {node.name}
                    </Text>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Edges */}
          {result.edges.length > 0 && (
            <div className="flex flex-col gap-2">
              <Text
                as="p"
                mainContentMuted
                text03
                className="text-xs font-medium uppercase tracking-wide"
              >
                Relationships ({result.edges.length})
              </Text>
              <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto pr-1">
                {result.edges.map((edge) => {
                  const srcNode = result.nodes.find(
                    (n) => n.id === edge.source
                  );
                  const tgtNode = result.nodes.find(
                    (n) => n.id === edge.target
                  );
                  return (
                    <div
                      key={edge.id}
                      className="flex items-center gap-2 rounded-08 border border-border-01 bg-background-tint-00 px-3 py-2 flex-wrap"
                    >
                      <Text as="p" mainUiAction text04 className="text-sm">
                        {srcNode?.name ?? edge.source}
                      </Text>
                      <Text
                        as="p"
                        mainContentMuted
                        text03
                        className="text-xs font-mono"
                      >
                        —{edge.type}→
                      </Text>
                      <Text as="p" mainUiAction text04 className="text-sm">
                        {tgtNode?.name ?? edge.target}
                      </Text>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {result.nodes.length === 0 &&
            result.edges.length === 0 &&
            !result.context && (
              <Text
                as="p"
                mainContentMuted
                text03
                className="text-sm text-center py-4"
              >
                No results found.
              </Text>
            )}
        </div>
      )}
    </CardSection>
  );
}
