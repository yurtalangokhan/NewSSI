"use client";

import React from "react";
import { Wrench, ChevronRightIcon, ChevronDown } from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { ToolCard, ToolCardLoading } from "./components/tool-card";
import { useMCPContext } from "@/providers/MCP";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import _ from "lodash";
import { Search } from "@/components/ui/tool-search";
import { useSearchTools } from "@/hooks/use-search-tools";
import { groupToolsByCategory, buildCategoryLabelMap } from "@/types/tool";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

function getCategoryLabel(category: string, labelMap: Record<string, string>): string {
  return labelMap[category] || `📦 ${_.startCase(category)}`;
}

function TotalToolsBadge({
  toolsCount,
  loading,
  hasMore,
}: {
  toolsCount: number;
  loading: boolean;
  hasMore: boolean;
}) {
  return (
    <span className="flex items-center gap-2">
      {loading ? (
        <Badge variant="outline">Loading...</Badge>
      ) : (
        <Badge variant="outline">
          {toolsCount}
          {hasMore && "+"}
        </Badge>
      )}
    </span>
  );
}

/**
 * The parent component containing the tools interface.
 */
export default function ToolsInterface(): React.ReactNode {
  const { tools, loading, getTools, cursor, setTools } = useMCPContext();
  const { toolSearchTerm, debouncedSetSearchTerm, filteredTools } =
    useSearchTools(tools);
  const [loadingMore, setLoadingMore] = React.useState(false);

  const handleLoadMore = async () => {
    if (!cursor) return;

    setLoadingMore(true);
    try {
      const newTools = await getTools(cursor);
      setTools((prevTools) => [...prevTools, ...newTools]);
    } catch (error) {
      console.error("Error loading more tools:", error);
    } finally {
      setLoadingMore(false);
    }
  };

  const groupedTools = React.useMemo(
    () => groupToolsByCategory(filteredTools),
    [filteredTools],
  );
  const categoryLabelMap = React.useMemo(
    () => buildCategoryLabelMap(filteredTools),
    [filteredTools],
  );
  const sortedCategories = React.useMemo(
    () =>
      Object.keys(groupedTools).sort((a, b) => {
        if (a === "other") return 1;
        if (b === "other") return -1;
        return getCategoryLabel(a, categoryLabelMap).localeCompare(getCategoryLabel(b, categoryLabelMap));
      }),
    [groupedTools, categoryLabelMap],
  );

  return (
    <div className="flex w-full flex-col gap-4 p-6">
      <div className="flex w-full items-center justify-start gap-6">
        <div className="flex items-center justify-start gap-2">
          <Wrench className="size-6" />
          <p className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            Tools
            <TotalToolsBadge
              toolsCount={tools.length}
              loading={loading}
              hasMore={!!cursor}
            />
          </p>
        </div>
        <Search
          onSearchChange={debouncedSetSearchTerm}
          placeholder="Search tools..."
          className="w-full"
        />
      </div>

      <Separator />

      {loading && !filteredTools.length && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <ToolCardLoading key={`tool-card-loading-${index}`} />
          ))}
        </div>
      )}

      {sortedCategories.map((category) => (
        <Collapsible
          key={category}
          defaultOpen={true}
        >
          <CollapsibleTrigger className="group flex w-full items-center gap-2 rounded-md px-2 py-2 hover:bg-slate-100">
            <ChevronDown className="size-4 transition-transform group-data-[state=closed]:-rotate-90" />
            <span className="text-base font-semibold">
              {getCategoryLabel(category, categoryLabelMap)}
            </span>
            <Badge
              variant="secondary"
              className="ml-1 text-xs"
            >
              {groupedTools[category].length}
            </Badge>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="grid grid-cols-1 gap-4 px-2 pb-4 pt-2 md:grid-cols-2 lg:grid-cols-3">
              {groupedTools[category].map((tool, index) => (
                <ToolCard
                  key={`${tool.name}-${index}`}
                  tool={tool}
                />
              ))}
            </div>
          </CollapsibleContent>
        </Collapsible>
      ))}

      {filteredTools.length === 0 && toolSearchTerm && (
        <p className="my-4 w-full text-center text-sm text-slate-500">
          No tools found matching &quot;{toolSearchTerm}&quot;.
        </p>
      )}
      {tools.length === 0 && !toolSearchTerm && !loading && (
        <p className="my-4 w-full text-center text-sm text-slate-500">
          No tools available for this agent.
        </p>
      )}

      {!toolSearchTerm && cursor && (
        <div className="mt-4 flex justify-center">
          <Button
            onClick={handleLoadMore}
            disabled={loadingMore}
            variant="outline"
            className="gap-1 px-2.5"
          >
            {loadingMore ? "Loading..." : "Load More Tools"}
            <ChevronRightIcon className="h-4 w-4" />
          </Button>
        </div>
      )}

      {loadingMore && (
        <div className="mt-4 flex justify-center">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <ToolCardLoading key={`tool-card-loading-more-${index}`} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
