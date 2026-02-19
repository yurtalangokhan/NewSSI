/**
 * Entity Preview – shows detail for a selected node including its
 * properties and adjacent relationships.
 */

"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { X, ArrowRight, ArrowLeft, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { GraphNode, GraphEdge } from "@/types/graph";

interface EntityPreviewProps {
  node: GraphNode | null;
  edges: GraphEdge[];
  nodes: GraphNode[];
  onClose: () => void;
  onNodeSelect?: (node: GraphNode) => void;
}

export function EntityPreview({
  node,
  edges,
  nodes,
  onClose,
  onNodeSelect,
}: EntityPreviewProps) {
  if (!node) return null;

  // Find edges connected to this node
  const outgoing = edges.filter((e) => e.source === node.id);
  const incoming = edges.filter((e) => e.target === node.id);
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <CardTitle className="text-sm font-medium">{node.name}</CardTitle>
            <Badge variant="secondary" className="text-xs">{node.label}</Badge>
            <span className="text-xs text-muted-foreground">
              ID: {node.id.slice(0, 12)}...
            </span>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} className="h-6 w-6">
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {/* Horizontal 3-column layout */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {/* Properties */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Info className="h-3 w-3" />
              Properties ({node.properties ? Object.keys(node.properties).length : 0})
            </div>
            {node.properties && Object.keys(node.properties).length > 0 ? (
              <ScrollArea className="h-[160px]">
                <div className="space-y-1 pr-2">
                  {Object.entries(node.properties).map(([key, value]) => (
                    <div
                      key={key}
                      className="grid grid-cols-[100px_1fr] gap-2 rounded px-2 py-1 text-xs even:bg-muted/50"
                    >
                      <span className="font-medium text-muted-foreground truncate">
                        {key}
                      </span>
                      <span className="break-words">
                        {typeof value === "object"
                          ? JSON.stringify(value)
                          : String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            ) : (
              <p className="text-xs text-muted-foreground">No properties</p>
            )}
          </div>

          {/* Outgoing Relationships */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <ArrowRight className="h-3 w-3" />
              Outgoing ({outgoing.length})
            </div>
            {outgoing.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No outgoing relationships
              </p>
            ) : (
              <ScrollArea className="h-[160px]">
                <div className="space-y-1 pr-2">
                  {outgoing.map((edge, i) => {
                    const target = nodeMap.get(edge.target);
                    return (
                      <div
                        key={i}
                        className="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-xs transition-colors hover:bg-muted/50"
                        onClick={() => target && onNodeSelect?.(target)}
                      >
                        <Badge variant="outline" className="text-[10px] shrink-0">
                          {edge.type}
                        </Badge>
                        <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
                        <span className="font-medium truncate">
                          {target?.name ?? edge.target.slice(0, 12)}
                        </span>
                        {target && (
                          <Badge
                            variant="secondary"
                            className="ml-auto text-[10px] shrink-0"
                          >
                            {target.label}
                          </Badge>
                        )}
                      </div>
                    );
                  })}
                </div>
              </ScrollArea>
            )}
          </div>

          {/* Incoming Relationships */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <ArrowLeft className="h-3 w-3" />
              Incoming ({incoming.length})
            </div>
            {incoming.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No incoming relationships
              </p>
            ) : (
              <ScrollArea className="h-[160px]">
                <div className="space-y-1 pr-2">
                  {incoming.map((edge, i) => {
                    const source = nodeMap.get(edge.source);
                    return (
                      <div
                        key={i}
                        className="flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-xs transition-colors hover:bg-muted/50"
                        onClick={() => source && onNodeSelect?.(source)}
                      >
                        <span className="font-medium truncate">
                          {source?.name ?? edge.source.slice(0, 12)}
                        </span>
                        <ArrowRight className="h-3 w-3 text-muted-foreground" />
                        <Badge variant="outline" className="text-[10px]">
                          {edge.type}
                        </Badge>
                        {source && (
                          <Badge
                            variant="secondary"
                            className="ml-auto text-[10px]"
                          >
                            {source.label}
                          </Badge>
                        )}
                      </div>
                    );
                  })}
                </div>
              </ScrollArea>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
