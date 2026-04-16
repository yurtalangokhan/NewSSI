"use client";

import { useState } from "react";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { ThreeDotsLoader } from "@/components/Loading";
import { toast } from "@/hooks/useToast";
import { searchDocuments, type SearchResult } from "@/lib/langconnect";
import { SvgSearch } from "@opal/icons";
import { cn } from "@/lib/utils";

interface SearchPanelProps {
  collectionId: string | null;
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 80
      ? "bg-status-success-subtle border-status-success text-status-success"
      : pct >= 50
      ? "bg-status-warning-subtle border-status-warning text-status-warning"
      : "bg-background-neutral-01 border-border-01 text-text-03";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold shrink-0",
        color
      )}
    >
      {pct}% match
    </span>
  );
}

function ResultCard({
  result,
  index,
}: {
  result: SearchResult;
  index: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const PREVIEW_LEN = 300;
  const isLong = result.page_content.length > PREVIEW_LEN;
  const displayText =
    !expanded && isLong
      ? result.page_content.slice(0, PREVIEW_LEN) + "…"
      : result.page_content;

  const metaEntries = Object.entries(result.metadata ?? {}).filter(
    ([k]) => k !== "chunk_id"
  );

  return (
    <div className="rounded-08 border border-border-01 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 bg-background-neutral-01 px-4 py-2.5 border-b border-border-01">
        <Text as="p" mainContentMuted text03 className="text-xs font-mono">
          #{index + 1}
        </Text>
        <ScoreBadge score={result.score} />
      </div>

      {/* Content */}
      <div className="px-4 py-3 flex flex-col gap-2">
        <Text
          as="p"
          mainContentBody
          text04
          className="whitespace-pre-wrap break-words leading-relaxed text-sm"
        >
          {displayText}
        </Text>
        {isLong && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="self-start text-xs text-action-link-05 hover:underline underline-offset-2"
          >
            {expanded ? "Show less" : "Show more"}
          </button>
        )}
      </div>

      {/* Metadata */}
      {metaEntries.length > 0 && (
        <div className="border-t border-border-01 bg-background-neutral-01 px-4 py-2 flex flex-wrap gap-x-4 gap-y-1">
          {metaEntries.map(([k, v]) => (
            <div key={k} className="flex items-center gap-1">
              <Text as="span" mainContentMuted text03 className="text-xs">
                {k}:
              </Text>
              <Text as="span" mainUiAction text03 className="text-xs font-mono">
                {String(v)}
              </Text>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SearchPanel({ collectionId }: SearchPanelProps) {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(10);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  async function handleSearch() {
    const q = query.trim();
    if (!collectionId || !q) return;
    setIsSearching(true);
    try {
      const data = await searchDocuments(collectionId, { query: q, limit });
      setResults(data);
      setHasSearched(true);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Search failed");
    } finally {
      setIsSearching(false);
    }
  }

  if (!collectionId) {
    return (
      <CardSection>
        <Text as="p" mainContentMuted text03 className="text-center py-6">
          Select a collection above to search documents.
        </Text>
      </CardSection>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <CardSection className="flex flex-col gap-4">
        <Text
          as="p"
          headingH3
          text05
          className="border-b border-border-01 pb-2"
        >
          Semantic Search
        </Text>
        <Text as="p" mainContentBody text04 className="leading-relaxed">
          Search documents using vector similarity. Results are ranked by cosine
          similarity to your query.
        </Text>

        {/* Search bar */}
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <InputTypeIn
              placeholder="Enter search query…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSearch();
              }}
            />
          </div>

          {/* Limit selector */}
          <div className="flex flex-col gap-0.5">
            <Text as="p" mainContentMuted text03 className="text-xs">
              Top K
            </Text>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className={cn(
                "h-9 rounded-08 border border-border-01 bg-background-neutral-01",
                "px-2 text-sm text-text-04 focus:outline-none focus:ring-1 focus:ring-action-primary"
              )}
            >
              {[5, 10, 20, 50].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>

          <Button
            action
            leftIcon={SvgSearch}
            onClick={handleSearch}
            disabled={isSearching || !query.trim()}
          >
            {isSearching ? "Searching…" : "Search"}
          </Button>
        </div>
      </CardSection>

      {/* Results */}
      {isSearching && (
        <CardSection className="flex items-center justify-center py-8">
          <ThreeDotsLoader />
        </CardSection>
      )}

      {!isSearching && hasSearched && (
        <CardSection className="flex flex-col gap-3">
          <div className="flex items-center justify-between border-b border-border-01 pb-2">
            <Text as="p" headingH3 text05>
              Results
            </Text>
            <Text as="p" mainContentMuted text03 className="text-sm">
              {results.length} result{results.length !== 1 ? "s" : ""}
            </Text>
          </div>

          {results.length === 0 ? (
            <Text as="p" mainContentMuted text03 className="text-center py-6">
              No results found for &ldquo;{query}&rdquo;.
            </Text>
          ) : (
            <div className="flex flex-col gap-3">
              {results.map((r, i) => (
                <ResultCard key={r.id} result={r} index={i} />
              ))}
            </div>
          )}
        </CardSection>
      )}
    </div>
  );
}
