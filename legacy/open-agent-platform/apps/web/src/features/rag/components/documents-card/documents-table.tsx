"use client";

import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Trash2, MoreVertical, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { Document } from "@langchain/core/documents";
import { useRagContext } from "../../providers/RAG";
import { format } from "date-fns";
import { Collection } from "@/types/collection";
import { getCollectionName } from "../../hooks/use-rag";

interface DocumentsTableProps {
  documents: Document[];
  selectedCollection: Collection;
  actionsDisabled: boolean;
}

function DocumentChunksRow({ 
  document, 
  collectionId, 
  colSpan 
}: { 
  document: Document; 
  collectionId: string; 
  colSpan: number 
}) {
  const { getDocumentChunks } = useRagContext();
  const [chunksData, setChunksData] = useState<{ chunks: any[], stats: any } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const fetchChunks = async () => {
      try {
        const data = await getDocumentChunks(collectionId, document.metadata.file_id);
        if (mounted) {
          setChunksData(data);
          setLoading(false);
        }
      } catch (error) {
        console.error("Failed to fetch chunks:", error);
        if (mounted) setLoading(false);
      }
    };
    fetchChunks();
    return () => { mounted = false; };
  }, [collectionId, document.metadata.file_id, getDocumentChunks]);

  if (loading) {
    return (
      <TableRow className="bg-muted/10">
        <TableCell colSpan={colSpan} className="p-4">
          <div className="flex items-center justify-center p-4">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mr-2" />
            <span className="text-sm text-muted-foreground">Loading chunks...</span>
          </div>
        </TableCell>
      </TableRow>
    );
  }

  if (!chunksData || !chunksData.chunks || chunksData.chunks.length === 0) {
    return (
      <TableRow className="bg-muted/10">
        <TableCell colSpan={colSpan} className="p-4">
          <div className="text-center text-sm text-muted-foreground p-4">
            No chunks found for this document.
          </div>
        </TableCell>
      </TableRow>
    );
  }
  
  const { chunks, stats } = chunksData;

  return (
    <TableRow className="bg-muted/10 border-b">
      <TableCell colSpan={colSpan} className="p-0 border-b-0">
        <div className="p-4 space-y-4">
          {/* Aggregate Stats */}
          <div className="grid grid-cols-3 gap-4 mb-3">
            <div className="rounded-lg border bg-background p-3 text-center">
              <p className="text-xl font-bold">{stats?.total_chunks || 0}</p>
              <p className="text-xs text-muted-foreground">Total Chunks</p>
            </div>
            <div className="rounded-lg border bg-background p-3 text-center">
              <p className="text-xl font-bold">~{stats?.avg_tokens || 0}</p>
              <p className="text-xs text-muted-foreground">Avg Tokens/Chunk</p>
            </div>
            <div className="rounded-lg border bg-background p-3 text-center">
              <p className="text-xl font-bold">{stats?.avg_chars || 0}</p>
              <p className="text-xs text-muted-foreground">Avg Chars/Chunk</p>
            </div>
          </div>
          
          {/* Chunks List */}
          <ScrollArea className="h-[300px] rounded-md border bg-background">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-background shadow-sm border-b z-10">
                <tr>
                  <th className="h-10 px-4 text-left font-medium w-16">#</th>
                  <th className="h-10 px-4 text-left font-medium">Content</th>
                  <th className="h-10 px-4 text-right font-medium w-24">Tokens</th>
                  <th className="h-10 px-4 text-right font-medium w-24">Chars</th>
                </tr>
              </thead>
              <tbody>
                {chunks.map((chunk: any, i: number) => {
                  const chars = chunk.content?.length || 0;
                  const tokens = chunk.metadata?.token_count || Math.ceil(chars / 4);
                  return (
                    <tr key={chunk.id || i} className="border-b last:border-0 hover:bg-muted/30">
                      <td className="p-4 align-top text-muted-foreground">
                        {i + 1}
                      </td>
                      <td className="p-4 align-top">
                        <p className="text-sm border rounded-md p-3 bg-muted/20 break-words whitespace-pre-wrap font-mono text-xs">
                          {chunk.content}
                        </p>
                      </td>
                      <td className="p-4 align-top text-right font-mono text-xs text-muted-foreground">
                        ~{tokens.toLocaleString()}
                      </td>
                      <td className="p-4 align-top text-right font-mono text-xs text-muted-foreground">
                        {chars.toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </ScrollArea>
        </div>
      </TableCell>
    </TableRow>
  );
}

export function DocumentsTable({
  documents,
  selectedCollection,
  actionsDisabled,
}: DocumentsTableProps) {
  const { deleteDocument } = useRagContext();
  const [expandedDocs, setExpandedDocs] = useState<Set<string>>(new Set());

  const toggleExpand = (docId: string) => {
    setExpandedDocs((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  };

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-10"></TableHead>
          <TableHead>Document Name</TableHead>
          <TableHead>Collection</TableHead>
          <TableHead>Date Uploaded</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {documents.length === 0 ? (
          <TableRow>
            <TableCell
              colSpan={5}
              className="text-muted-foreground text-center py-8"
            >
              No documents found in this collection.
            </TableCell>
          </TableRow>
        ) : (
          documents.map((doc) => {
            const docId = doc.metadata.file_id;
            const isExpanded = expandedDocs.has(docId);
            return (
              <React.Fragment key={doc.id}>
                <TableRow className={isExpanded ? "border-b-0 hover:bg-transparent" : ""}>
                  <TableCell className="pl-4">
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      className="h-6 w-6 rounded-md" 
                      onClick={() => toggleExpand(docId)}
                    >
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </Button>
                  </TableCell>
                  <TableCell className="font-medium">{doc.metadata.name}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="font-normal">
                      {getCollectionName(selectedCollection.name)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {format(new Date(doc.metadata.created_at), "MM/dd/yyyy h:mm a")}
                  </TableCell>
                  <TableCell className="text-right">
                    <AlertDialog>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                          >
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <AlertDialogTrigger asChild>
                            <DropdownMenuItem
                              className="text-destructive focus:bg-destructive focus:text-destructive-foreground cursor-pointer"
                              disabled={actionsDisabled}
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              Delete
                            </DropdownMenuItem>
                          </AlertDialogTrigger>
                        </DropdownMenuContent>
                      </DropdownMenu>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>
                            Are you absolutely sure?
                          </AlertDialogTitle>
                          <AlertDialogDescription>
                            This action cannot be undone. This will permanently
                            delete the document
                            <span className="font-semibold text-foreground">
                              {" "}
                              {doc.metadata.name}
                            </span>
                            .
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={async () =>
                              await deleteDocument(doc.metadata.file_id)
                            }
                            className="bg-destructive hover:bg-destructive/90 text-destructive-foreground"
                            disabled={actionsDisabled}
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </TableCell>
                </TableRow>
                {isExpanded && (
                  <DocumentChunksRow 
                    document={doc} 
                    collectionId={selectedCollection.uuid} 
                    colSpan={5} 
                  />
                )}
              </React.Fragment>
            );
          })
        )}
      </TableBody>
    </Table>
  );
}
