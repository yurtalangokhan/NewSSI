/**
 * Graph Search component – hybrid vector + graph search with optional Cypher query editor.
 */

"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Search, Terminal, ArrowRight } from "lucide-react";
import { useGraphSearch } from "../hooks/use-graph-rag";
import type {
  GraphSearchResult,
  CypherQueryResult,
  GraphNode,
} from "@/types/graph";

interface GraphSearchProps {
  collectionId: string;
  onNodeSelect?: (node: GraphNode) => void;
}

export function GraphSearch({ collectionId, onNodeSelect }: GraphSearchProps) {
  // Hybrid search state
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(10);
  const [vectorWeight, setVectorWeight] = useState(0.6);

  // Cypher state
  const [cypherQuery, setCypherQuery] = useState("MATCH (n) RETURN n LIMIT 25");
  const [cypherResult, setCypherResult] = useState<CypherQueryResult | null>(
    null,
  );

  // Entity search state
  const [entityQuery, setEntityQuery] = useState("");
  const [entityResults, setEntityResults] = useState<GraphNode[]>([]);

  const {
    search,
    searchEntities,
    executeCypher,
    searchResults,
    searching,
  } = useGraphSearch();

  const handleHybridSearch = async () => {
    if (!query.trim()) return;
    await search({
      collection_id: collectionId,
      query: query.trim(),
      limit,
      search_type: "hybrid",
      vector_weight: vectorWeight,
      graph_weight: 1 - vectorWeight,
    });
  };

  const handleEntitySearch = async () => {
    if (!entityQuery.trim()) return;
    const results = await searchEntities(collectionId, entityQuery.trim(), limit);
    if (results && results.nodes) {
      setEntityResults(results.nodes);
    } else if (results && Array.isArray(results)) {
      setEntityResults(results);
    }
  };

  const handleCypherExecute = async () => {
    if (!cypherQuery.trim()) return;
    const result = await executeCypher({
      collection_id: collectionId,
      query: cypherQuery.trim(),
    });
    if (result) setCypherResult(result);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Graph Search</CardTitle>
        <CardDescription>
          Search the knowledge graph using hybrid retrieval, entity lookup, or
          raw Cypher queries.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="hybrid" className="space-y-4">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="hybrid" className="text-xs">
              <Search className="mr-1.5 h-3.5 w-3.5" />
              Hybrid Search
            </TabsTrigger>
            <TabsTrigger value="entity" className="text-xs">
              <ArrowRight className="mr-1.5 h-3.5 w-3.5" />
              Entity Search
            </TabsTrigger>
            <TabsTrigger value="cypher" className="text-xs">
              <Terminal className="mr-1.5 h-3.5 w-3.5" />
              Cypher
            </TabsTrigger>
          </TabsList>

          {/* ─── Hybrid Search ──────────────────────────────── */}
          <TabsContent value="hybrid" className="space-y-4">
            <div className="flex items-end gap-2">
              <div className="flex-1 space-y-1">
                <Label className="text-xs">Query</Label>
                <Input
                  placeholder="Ask about relationships, entities, or facts..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleHybridSearch()}
                  className="h-8"
                />
              </div>
              <Button
                size="sm"
                onClick={handleHybridSearch}
                disabled={searching || !query.trim()}
              >
                {searching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </div>

            {/* Search params */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label className="text-xs">Limit: {limit}</Label>
                <Slider
                  value={[limit]}
                  onValueChange={([v]) => setLimit(v)}
                  min={1}
                  max={50}
                  step={1}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">
                  Vector Weight: {vectorWeight.toFixed(2)} / Graph:{" "}
                  {(1 - vectorWeight).toFixed(2)}
                </Label>
                <Slider
                  value={[vectorWeight]}
                  onValueChange={([v]) => setVectorWeight(v)}
                  min={0}
                  max={1}
                  step={0.05}
                />
              </div>
            </div>

            {/* Results */}
            {searchResults && (
              <ScrollArea className="h-[300px] rounded-md border">
                <div className="space-y-2 p-3">
                  <SearchResultDisplay result={searchResults} onNodeSelect={onNodeSelect} />
                </div>
              </ScrollArea>
            )}
          </TabsContent>

          {/* ─── Entity Search ─────────────────────────────── */}
          <TabsContent value="entity" className="space-y-4">
            <div className="flex items-end gap-2">
              <div className="flex-1 space-y-1">
                <Label className="text-xs">Entity Name</Label>
                <Input
                  placeholder="Search for entities by name..."
                  value={entityQuery}
                  onChange={(e) => setEntityQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleEntitySearch()}
                  className="h-8"
                />
              </div>
              <Button
                size="sm"
                onClick={handleEntitySearch}
                disabled={searching || !entityQuery.trim()}
              >
                {searching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </div>

            {entityResults.length > 0 && (
              <ScrollArea className="h-[300px] rounded-md border">
                <div className="space-y-1 p-3">
                  {entityResults.map((node, i) => (
                    <div
                      key={i}
                      className="flex cursor-pointer items-center justify-between rounded-md border p-2 transition-colors hover:bg-muted/50"
                      onClick={() => onNodeSelect?.(node)}
                    >
                      <div>
                        <span className="text-sm font-medium">{node.name}</span>
                        <Badge variant="outline" className="ml-2 text-xs">
                          {node.label}
                        </Badge>
                      </div>
                      {node.properties &&
                        Object.keys(node.properties).length > 0 && (
                          <span className="text-xs text-muted-foreground">
                            {Object.keys(node.properties).length} props
                          </span>
                        )}
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </TabsContent>

          {/* ─── Cypher ────────────────────────────────────── */}
          <TabsContent value="cypher" className="space-y-4">
            <div className="space-y-1">
              <Label className="text-xs">Cypher Query</Label>
              <Textarea
                value={cypherQuery}
                onChange={(e) => setCypherQuery(e.target.value)}
                placeholder="MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 25"
                className="font-mono text-xs"
                rows={4}
              />
            </div>

            <Button
              size="sm"
              onClick={handleCypherExecute}
              disabled={searching || !cypherQuery.trim()}
              className="w-full"
            >
              {searching ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Terminal className="mr-2 h-4 w-4" />
              )}
              Execute
            </Button>

            {cypherResult && (
              <ScrollArea className="h-[300px] rounded-md border">
                <pre className="whitespace-pre-wrap p-3 text-xs">
                  {JSON.stringify(cypherResult.results, null, 2)}
                </pre>
              </ScrollArea>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

/* ─── Search Result Display ──────────────────────────────── */

function SearchResultDisplay({
  result,
  onNodeSelect,
}: {
  result: GraphSearchResult;
  onNodeSelect?: (node: GraphNode) => void;
}) {
  return (
    <div className="space-y-3">
      {/* Context summary */}
      {result.context && (
        <div className="rounded-md bg-muted/50 p-3">
          <p className="text-xs font-medium text-muted-foreground mb-1">Context</p>
          <p className="text-sm leading-relaxed">{result.context}</p>
        </div>
      )}

      {/* Score */}
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className="text-xs">
          Score: {result.score.toFixed(3)}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {result.nodes.length} nodes, {result.edges.length} edges
        </span>
      </div>

      {/* Matched nodes */}
      {result.nodes.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Matched Nodes</p>
          {result.nodes.map((node, i) => (
            <div
              key={i}
              className="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-xs transition-colors hover:bg-muted/50"
              onClick={() => onNodeSelect?.(node)}
            >
              <Badge variant="outline" className="text-[10px]">
                {node.label}
              </Badge>
              <span className="font-medium">{node.name}</span>
            </div>
          ))}
        </div>
      )}

      {/* Matched edges */}
      {result.edges.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Relationships</p>
          {result.edges.map((edge, i) => (
            <div
              key={i}
              className="flex items-center gap-2 rounded-md border px-2 py-1.5 text-xs"
            >
              <span>{edge.source.slice(0, 12)}…</span>
              <Badge variant="outline" className="text-[10px]">
                {edge.type}
              </Badge>
              <span>→ {edge.target.slice(0, 12)}…</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
