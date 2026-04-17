"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { BuiltInTool } from "@/lib/tools/interfaces";
import _ from "lodash";
import {
  parseToolCategory,
  groupToolsByCategory,
  buildCategoryLabelMap,
  ToolWithCategory,
} from "@/lib/tools/builtInToolUtils";
import { getBuiltInTools } from "@/lib/tools/mcpService";
import { toast } from "@/hooks/useToast";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/refresh-components/Collapsible";
import { Wrench, ChevronDown, Loader2, Search } from "lucide-react";
import { Input } from "@/components/ui/input";

interface BuiltInToolsSectionProps {
  onToolSelect?: (tool: BuiltInTool) => void;
}

function ToolCard({
  tool,
  onTest,
}: {
  tool: ToolWithCategory;
  onTest: (tool: ToolWithCategory) => void;
}) {
  return (
    <div className="border rounded-lg p-4 hover:bg-gray-50 transition-colors">
      <div className="flex items-center justify-between gap-2 mb-2">
        <h3 className="font-medium truncate">{_.startCase(tool.name)}</h3>
        {tool.category && (
          <Badge variant="secondary" className="shrink-0 text-xs">
            {tool.categoryLabel || tool.category}
          </Badge>
        )}
      </div>
      <p className="text-sm text-gray-600 line-clamp-2 mb-3">
        {tool.description || "No description"}
      </p>
      <button
        onClick={() => onTest(tool)}
        className="text-sm text-blue-600 hover:text-blue-800 font-medium"
      >
        Test Tool →
      </button>
    </div>
  );
}

function ToolCardSkeleton() {
  return (
    <div className="border rounded-lg p-4 animate-pulse">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="h-5 w-32 bg-gray-200 rounded" />
        <div className="h-5 w-16 bg-gray-200 rounded" />
      </div>
      <div className="h-4 w-full bg-gray-200 rounded mb-2" />
      <div className="h-4 w-3/4 bg-gray-200 rounded" />
    </div>
  );
}

export default function BuiltInToolsSection({
  onToolSelect,
}: BuiltInToolsSectionProps) {
  const router = useRouter();
  const [tools, setTools] = useState<BuiltInTool[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    async function fetchTools() {
      setIsLoading(true);
      try {
        const response = await getBuiltInTools();
        if (response.error) {
          setError(response.error);
          toast.error(response.error);
        } else {
          setTools(response.tools);
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "Failed to fetch tools";
        setError(errorMsg);
        toast.error(errorMsg);
      } finally {
        setIsLoading(false);
      }
    }

    fetchTools();
  }, []);

  const toolsWithCategory = useMemo(() => {
    return tools.map((tool) => parseToolCategory(tool));
  }, [tools]);

  const filteredTools = useMemo(() => {
    if (!searchQuery.trim()) return toolsWithCategory;
    const query = searchQuery.toLowerCase();
    return toolsWithCategory.filter(
      (tool) =>
        tool.name.toLowerCase().includes(query) ||
        tool.description?.toLowerCase().includes(query) ||
        tool.category?.toLowerCase().includes(query)
    );
  }, [toolsWithCategory, searchQuery]);

  const groupedTools = useMemo(() => {
    return groupToolsByCategory(filteredTools);
  }, [filteredTools]);

  const categoryLabelMap = useMemo(() => {
    return buildCategoryLabelMap(filteredTools);
  }, [filteredTools]);

  const sortedCategories = useMemo(() => {
    return Object.keys(groupedTools).sort((a, b) => {
      if (a === "other") return 1;
      if (b === "other") return -1;
      const labelA = categoryLabelMap[a] || a;
      const labelB = categoryLabelMap[b] || b;
      return labelA.localeCompare(labelB);
    });
  }, [groupedTools, categoryLabelMap]);

  const handleTestTool = useCallback(
    (tool: ToolWithCategory) => {
      const encodedTool = encodeURIComponent(tool.name);
      router.push(`/tools/playground?tool=${encodedTool}`);
    },
    [router]
  );

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between gap-4 mb-4">
        <div className="flex items-center gap-2">
          <Wrench className="size-5" />
          <h2 className="text-lg font-semibold">Built-in Tools</h2>
          <Badge variant="outline">{tools.length}</Badge>
        </div>
        <div className="relative w-64">
          <Search className="absolute left-2.5 top-2.5 size-4 text-gray-500" />
          <Input
            type="text"
            placeholder="Search tools..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="size-6 animate-spin mr-2" />
          <span>Loading tools...</span>
        </div>
      )}

      {error && !isLoading && (
        <div className="text-center py-8 text-red-600">{error}</div>
      )}

      {!isLoading && !error && tools.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          <Wrench className="size-8 mx-auto mb-2 opacity-50" />
          <p>No built-in tools available yet</p>
          <p className="text-sm mt-1">Tools will appear here once the tools-service is configured</p>
        </div>
      )}

      {!isLoading && !error && tools.length > 0 && (
        <div className="flex-1 overflow-y-auto">
          {sortedCategories.map((category) => (
            <Collapsible key={category} defaultOpen={true}>
              <CollapsibleTrigger className="group flex w-full items-center gap-2 rounded-md px-2 py-2 hover:bg-slate-100 text-left">
                <ChevronDown className="size-4 transition-transform group-data-[state=closed]:-rotate-90" />
                <span className="text-base font-semibold">
                  {categoryLabelMap[category] || category}
                </span>
                <Badge variant="secondary" className="ml-1 text-xs">
                  {(groupedTools[category] ?? []).length}
                </Badge>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 px-2 pb-4 pt-2">
                  {(groupedTools[category] ?? []).map((tool) => (
                    <ToolCard
                      key={tool.name}
                      tool={tool}
                      onTest={handleTestTool}
                    />
                  ))}
                </div>
              </CollapsibleContent>
            </Collapsible>
          ))}
        </div>
      )}

    </div>
  );
}