"use client";

import { useState, useEffect } from "react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Database, Sparkles, Clock, AlertCircle } from "lucide-react";
import { ConfigTree } from "./config-tree";

interface DataSourceDetailsDialogProps {
    dataSourceId: string | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    getDataSourceDetails: (id: string) => Promise<any>;
}

export function DataSourceDetailsDialog({
    dataSourceId,
    open,
    onOpenChange,
    getDataSourceDetails,
}: DataSourceDetailsDialogProps) {
    const [details, setDetails] = useState<any>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (open && dataSourceId) {
            setLoading(true);
            getDataSourceDetails(dataSourceId)
                .then(setDetails)
                .finally(() => setLoading(false));
        }
    }, [open, dataSourceId, getDataSourceDetails]);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl max-h-[80vh]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Database className="h-5 w-5" />
                        {details?.name || "Data Source Details"}
                    </DialogTitle>
                </DialogHeader>

                {loading ? (
                    <div className="flex items-center justify-center py-8">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                    </div>
                ) : details ? (
                    <Tabs defaultValue="config" className="w-full">
                        <TabsList className="grid w-full grid-cols-3">
                            <TabsTrigger value="config">Configuration</TabsTrigger>
                            <TabsTrigger value="chunks">Chunks ({details.chunk_count ?? details.document_count})</TabsTrigger>
                            <TabsTrigger value="status">Status</TabsTrigger>
                        </TabsList>

                        <TabsContent value="config" className="space-y-4 mt-4">
                            <div className="grid gap-3">
                                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                    <span className="text-sm font-medium">Connector</span>
                                    <Badge variant="outline">{details.connector_display_name}</Badge>
                                </div>
                                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                    <span className="text-sm font-medium">Connector Type</span>
                                    <code className="text-xs bg-background px-2 py-1 rounded">
                                        {details.connector_type}
                                    </code>
                                </div>
                                {details.streams && details.streams.length > 0 && (
                                    <div className="p-3 rounded-lg bg-muted/50">
                                        <span className="text-sm font-medium block mb-2">Synced Streams</span>
                                        <div className="flex flex-wrap gap-1">
                                            {details.streams.map((stream: string) => (
                                                <Badge key={stream} variant="secondary" className="text-xs">
                                                    {stream}
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {details.config && Object.keys(details.config).length > 0 && (
                                    <div className="p-3 rounded-lg bg-muted/50">
                                        <span className="text-sm font-medium block mb-2">Configuration</span>
                                        <ConfigTree data={details.config} />
                                    </div>
                                )}
                            </div>
                        </TabsContent>

                        <TabsContent value="chunks" className="mt-4">
                            {/* Aggregate Stats */}
                            {(details.chunk_count ?? details.document_count) > 0 && (
                                <div className="grid grid-cols-3 gap-2 mb-3">
                                    <div className="rounded-lg border bg-muted/30 p-2 text-center">
                                        <p className="text-lg font-bold">{details.chunk_count ?? details.document_count}</p>
                                        <p className="text-[10px] text-muted-foreground">Chunks</p>
                                    </div>
                                    <div className="rounded-lg border bg-muted/30 p-2 text-center">
                                        <p className="text-lg font-bold">{details.avg_chunk_tokens ?? '—'}</p>
                                        <p className="text-[10px] text-muted-foreground">Avg Tokens</p>
                                    </div>
                                    <div className="rounded-lg border bg-muted/30 p-2 text-center">
                                        <p className="text-lg font-bold">{details.avg_chunk_chars ?? '—'}</p>
                                        <p className="text-[10px] text-muted-foreground">Avg Chars</p>
                                    </div>
                                </div>
                            )}
                            <ScrollArea className="h-[240px]">
                                {(details.chunks ?? details.sample_documents)?.length > 0 ? (
                                    <div className="rounded-md border">
                                        <table className="w-full text-sm">
                                            <thead>
                                                <tr className="border-b bg-muted/50">
                                                    <th className="h-10 px-3 text-left font-medium w-10">#</th>
                                                    <th className="h-10 px-3 text-left font-medium">Content</th>
                                                    <th className="h-10 px-3 text-right font-medium w-16">Tokens</th>
                                                    <th className="h-10 px-3 text-right font-medium w-16">Chars</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {(details.chunks ?? details.sample_documents).slice(0, 5).map((chunk: any, i: number) => (
                                                    <tr key={i} className="border-b last:border-0 hover:bg-muted/30">
                                                        <td className="p-3 align-top text-muted-foreground">
                                                            {i + 1}
                                                        </td>
                                                        <td className="p-3 align-top">
                                                            <p className="text-sm line-clamp-2 whitespace-pre-wrap">
                                                                {chunk.content}
                                                            </p>
                                                        </td>
                                                        <td className="p-3 align-top text-right font-mono text-xs">
                                                            {chunk.token_count?.toLocaleString() ?? '—'}
                                                        </td>
                                                        <td className="p-3 align-top text-right font-mono text-xs">
                                                            {chunk.char_count?.toLocaleString() ?? '—'}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                        {(details.chunk_count ?? details.document_count) > 5 && (
                                            <div className="p-3 text-center text-sm text-muted-foreground border-t bg-muted/30">
                                                Showing 5 of {details.chunk_count ?? details.document_count} chunks
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                                        <Sparkles className="h-8 w-8 mb-2 opacity-50" />
                                        <p className="text-sm">No chunks indexed yet</p>
                                        <p className="text-xs">Sync this data source to index chunks</p>
                                    </div>
                                )}
                            </ScrollArea>
                        </TabsContent>

                        <TabsContent value="status" className="space-y-4 mt-4">
                            <div className="grid gap-3">
                                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                    <span className="text-sm font-medium flex items-center gap-2">
                                        <Clock className="h-4 w-4" />
                                        Created
                                    </span>
                                    <span className="text-sm">
                                        {details.created_at
                                            ? new Date(details.created_at).toLocaleString()
                                            : "Unknown"}
                                    </span>
                                </div>
                                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                    <span className="text-sm font-medium">Last Synced</span>
                                    <span className="text-sm">
                                        {details.last_synced_at
                                            ? new Date(details.last_synced_at).toLocaleString()
                                            : "Never"}
                                    </span>
                                </div>
                                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                    <span className="text-sm font-medium">Sync Status</span>
                                    <Badge variant={
                                        details.sync_status === "completed" ? "default" :
                                            details.sync_status === "error" ? "destructive" :
                                                "secondary"
                                    }>
                                        {details.sync_status || "idle"}
                                    </Badge>
                                </div>
                                {details.sync_progress > 0 && details.sync_progress < 100 && (
                                    <div className="p-3 rounded-lg bg-muted/50">
                                        <span className="text-sm font-medium block mb-2">Progress</span>
                                        <Progress value={details.sync_progress} className="h-2" />
                                    </div>
                                )}
                                {details.last_error && (
                                    <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20">
                                        <span className="text-sm font-medium flex items-center gap-2 text-destructive mb-2">
                                            <AlertCircle className="h-4 w-4" />
                                            Last Error
                                        </span>
                                        <p className="text-xs text-destructive/80">{details.last_error}</p>
                                    </div>
                                )}
                            </div>
                        </TabsContent>
                    </Tabs>
                ) : (
                    <div className="text-center py-8 text-muted-foreground">
                        Failed to load details
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
