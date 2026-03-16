"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CreateDataSourceDialog } from "./create-datasource-dialog";
import { ScheduleDialog, ScheduleBadge } from "./schedule-dialog";
import { useDataSources } from "@/hooks/use-datasources";
import type { SyncSchedule } from "@/hooks/use-datasources";
import {
    RefreshCw,
    Database,
    CheckCircle,
    AlertTriangle,
    Trash2,
    Loader2,
    Clock,
    AlertCircle,
    Sparkles,
    ChevronLeft,
    ChevronRight,
    Timer,
    GitGraph,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";

export function DataSourcePanel() {
    const {
        dataSources,
        loading,
        syncDataSource,
        deleteDataSource,
        getDataSourceDetails,
        getSyncStatus,
        refresh
    } = useDataSources();

    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
    const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());
    const [syncProgress, setSyncProgress] = useState<Record<string, { status: string; progress: number; graph_update_status?: string; queue_position?: number; last_error?: string }>>({});
    const [details, setDetails] = useState<any>(null);
    const [detailsLoading, setDetailsLoading] = useState(false);
    const [docPage, setDocPage] = useState(1);
    const [selectedSchedule, setSelectedSchedule] = useState<SyncSchedule | null>(null);
    const pageSize = 10;

    // Load details when selection or page changes
    useEffect(() => {
        if (selectedId) {
            setDetailsLoading(true);
            getDataSourceDetails(selectedId, docPage, pageSize)
                .then((detailsData) => {
                    setDetails(detailsData);
                    setSelectedSchedule(detailsData?.schedule || null);
                })
                .finally(() => setDetailsLoading(false));
        } else {
            setDetails(null);
            setSelectedSchedule(null);
            setDocPage(1);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedId, docPage]);

    // Poll sync status for active syncs
    const pollSyncStatus = useCallback(async (id: string) => {
        const status = await getSyncStatus(id);
        if (status) {
            setSyncProgress(prev => ({
                ...prev,
                [id]: {
                    status: status.sync_status,
                    progress: status.sync_progress,
                    graph_update_status: status.graph_update_status,
                    queue_position: status.queue_position,
                    last_error: status.last_error,
                }
            }));

            if (status.sync_status === "completed" || status.sync_status === "error") {
                // Keep polling briefly if graph is rebuilding
                if (status.graph_update_status === "graph_rebuilding") {
                    return;
                }
                // Show toast notification for completed/failed syncs
                if (status.sync_status === "error") {
                    toast.error("Sync failed", {
                        description: status.last_error || "An unknown error occurred during sync.",
                        duration: 8000,
                    });
                } else {
                    toast.success("Sync completed successfully");
                }
                setSyncingIds(prev => {
                    const next = new Set(prev);
                    next.delete(id);
                    return next;
                });
                refresh();
                // Re-fetch details if this datasource is currently selected
                if (id === selectedId) {
                    getDataSourceDetails(id, docPage, pageSize).then((d) => {
                        if (d) setDetails(d);
                    });
                }
            }
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedId, docPage]);

    useEffect(() => {
        const interval = setInterval(() => {
            syncingIds.forEach(id => pollSyncStatus(id));
        }, 1000);
        return () => clearInterval(interval);
    }, [syncingIds, pollSyncStatus]);

    const handleSync = async (id: string) => {
        setSyncingIds(prev => new Set(prev).add(id));
        setSyncProgress(prev => ({ ...prev, [id]: { status: "starting", progress: 0 } }));
        await syncDataSource(id);
    };

    const handleDelete = async () => {
        if (deleteConfirmId) {
            await deleteDataSource(deleteConfirmId);
            if (selectedId === deleteConfirmId) {
                setSelectedId(null);
                setSelectedSchedule(null);
            }
            setDeleteConfirmId(null);
        }
    };

    const getStatusIcon = (ds: any) => {
        const progress = syncProgress[ds.id];
        if (progress && progress.status !== "completed" && progress.status !== "error" && progress.status !== "idle") {
            return <Loader2 className="h-3 w-3 animate-spin text-blue-500" />;
        }
        // Check both polled progress state and list-level sync_status
        if (progress?.status === "error" || ds.sync_status === "error") {
            return <AlertTriangle className="h-3 w-3 text-red-500" />;
        }
        if (progress?.status === "completed" || ds.sync_status === "completed") {
            return <CheckCircle className="h-3 w-3 text-green-500" />;
        }
        return null;
    };

    return (
        <>
            <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
                {/* Left: Data Sources List */}
                <div className="md:col-span-1">
                    <Card className="h-full">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium">Data Sources</CardTitle>
                            <CreateDataSourceDialog onCreated={refresh} />
                        </CardHeader>
                        <CardContent className="space-y-4 pt-4">
                            {loading ? (
                                <div className="flex items-center justify-center py-8">
                                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                                </div>
                            ) : dataSources.length === 0 ? (
                                <div className="flex flex-col items-center justify-center p-8 text-muted-foreground border border-dashed rounded-md">
                                    <Database className="h-8 w-8 mb-2 opacity-50" />
                                    <p className="text-sm">No data sources configured</p>
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    {dataSources.map((ds) => {
                                        const progress = syncProgress[ds.id];
                                        const isSyncing = syncingIds.has(ds.id);
                                        const isSelected = selectedId === ds.id;

                                        return (
                                            <div
                                                key={ds.id}
                                                className={`rounded-lg border p-3 shadow-sm transition-colors cursor-pointer ${isSelected
                                                    ? "bg-primary/10 border-primary"
                                                    : "hover:bg-muted/50"
                                                    }`}
                                                onClick={() => {
                                                    if (selectedId !== ds.id) {
                                                        setDocPage(1); // Reset pagination when selecting new datasource
                                                    }
                                                    setSelectedId(ds.id);
                                                }}
                                            >
                                                <div className="flex items-center justify-between">
                                                    <div className="space-y-1 flex-1 min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <p className="font-medium text-sm truncate">{ds.name}</p>
                                                            <Badge variant="outline" className="text-xs shrink-0">
                                                                {ds.connector_display_name}
                                                            </Badge>
                                                        </div>
                                                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                                            {getStatusIcon(ds)}
                                                            <span>
                                                                {ds.last_synced_at
                                                                    ? `Synced: ${new Date(ds.last_synced_at).toLocaleDateString()}`
                                                                    : "Never synced"}
                                                            </span>
                                                            <ScheduleBadge schedule={ds.schedule_summary} />
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-7 w-7"
                                                            onClick={() => handleSync(ds.id)}
                                                            disabled={isSyncing}
                                                            title="Sync Now"
                                                        >
                                                            {isSyncing ? (
                                                                <Loader2 className="h-3 w-3 animate-spin" />
                                                            ) : (
                                                                <RefreshCw className="h-3 w-3" />
                                                            )}
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-7 w-7 text-destructive hover:text-destructive"
                                                            onClick={() => setDeleteConfirmId(ds.id)}
                                                            title="Delete"
                                                        >
                                                            <Trash2 className="h-3 w-3" />
                                                        </Button>
                                                    </div>
                                                </div>

                                                {/* Sync Progress */}
                                                {isSyncing && progress && (
                                                    <div className="mt-2 space-y-1">
                                                        <div className="flex items-center justify-between text-xs">
                                                            <span className="capitalize text-muted-foreground">
                                                                {progress.graph_update_status === "graph_rebuilding"
                                                                    ? "Rebuilding Graph RAG..."
                                                                    : progress.queue_position != null && progress.queue_position > 0
                                                                        ? `Queued (position ${progress.queue_position + 1})`
                                                                        : `${progress.status}...`}
                                                            </span>
                                                            <span className="text-muted-foreground">
                                                                {progress.progress}%
                                                            </span>
                                                        </div>
                                                        <Progress value={progress.progress} className="h-1" />
                                                    </div>
                                                )}
                                                {/* Inline error from last sync */}
                                                {!isSyncing && progress?.status === "error" && progress.last_error && (
                                                    <div className="mt-2 p-2 rounded bg-destructive/10 border border-destructive/20">
                                                        <p className="text-[11px] text-destructive line-clamp-2">
                                                            {progress.last_error}
                                                        </p>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>

                {/* Right: Details Panel */}
                <div className="md:col-span-2">
                    <Card className="h-full min-h-[400px]">
                        {!selectedId ? (
                            <div className="flex flex-col items-center justify-center h-full text-muted-foreground py-16">
                                <Database className="h-12 w-12 mb-4 opacity-30" />
                                <p className="text-sm">Select a data source to view details</p>
                            </div>
                        ) : detailsLoading ? (
                            <div className="flex items-center justify-center h-full py-16">
                                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                            </div>
                        ) : details ? (
                            <>
                                <CardHeader className="pb-2">
                                    <CardTitle className="flex items-center gap-2 text-lg">
                                        <Database className="h-5 w-5" />
                                        {details.name}
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <Tabs defaultValue="documents" className="w-full">
                                        <TabsList className="grid w-full grid-cols-4">
                                            <TabsTrigger value="documents">Documents ({details.document_count})</TabsTrigger>
                                            <TabsTrigger value="schedule">Schedule</TabsTrigger>
                                            <TabsTrigger value="config">Configuration</TabsTrigger>
                                            <TabsTrigger value="status">Status</TabsTrigger>
                                        </TabsList>

                                        {/* Documents Tab with Table */}
                                        <TabsContent value="documents" className="mt-4">
                                            <ScrollArea className="h-[350px]">
                                                {details.sample_documents?.length > 0 ? (
                                                    <Table>
                                                        <TableHeader>
                                                            <TableRow>
                                                                <TableHead className="w-[150px]">Title</TableHead>
                                                                <TableHead className="w-[120px]">Source</TableHead>
                                                                <TableHead>Content Preview</TableHead>
                                                            </TableRow>
                                                        </TableHeader>
                                                        <TableBody>
                                                            {details.sample_documents.map((doc: any, i: number) => {
                                                                // Parse content if needed to extract title/source
                                                                const parseContentField = (content: string, field: string): string | null => {
                                                                    const lines = content.split('\n');
                                                                    for (const line of lines) {
                                                                        if (line.toLowerCase().startsWith(`${field}:`)) {
                                                                            return line.substring(field.length + 1).trim();
                                                                        }
                                                                    }
                                                                    return null;
                                                                };
                                                                
                                                                // Try to get title/source from metadata first, then from content
                                                                const title = doc.metadata?.title 
                                                                    || parseContentField(doc.content, 'title') 
                                                                    || doc.metadata?.name 
                                                                    || '-';
                                                                const docSource = doc.metadata?.source 
                                                                    || parseContentField(doc.content, 'source') 
                                                                    || doc.metadata?.stream 
                                                                    || '-';
                                                                
                                                                // Get a clean content preview (remove parsed fields)
                                                                const contentPreview = doc.content
                                                                    .split('\n')
                                                                    .filter((line: string) => !line.toLowerCase().startsWith('title:') && !line.toLowerCase().startsWith('source:'))
                                                                    .join('\n')
                                                                    .trim()
                                                                    .substring(0, 200);
                                                                
                                                                return (
                                                                    <TableRow key={i}>
                                                                        <TableCell className="font-medium align-top">
                                                                            {title}
                                                                        </TableCell>
                                                                        <TableCell className="font-mono text-xs align-top">
                                                                            {docSource}
                                                                        </TableCell>
                                                                        <TableCell className="align-top">
                                                                            <p className="text-sm text-muted-foreground line-clamp-2 whitespace-pre-wrap">
                                                                                {contentPreview}{contentPreview.length >= 200 ? '...' : ''}
                                                                            </p>
                                                                        </TableCell>
                                                                    </TableRow>
                                                                );
                                                            })}
                                                        </TableBody>
                                                    </Table>
                                                ) : (
                                                    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                                                        <Sparkles className="h-8 w-8 mb-2 opacity-50" />
                                                        <p className="text-sm">No documents indexed yet</p>
                                                        <p className="text-xs">Sync this data source to index documents</p>
                                                    </div>
                                                )}
                                            </ScrollArea>
                                            {/* Pagination Controls */}
                                            {details.document_count > 0 && (
                                                <div className="flex items-center justify-between border-t pt-3 mt-3">
                                                    <p className="text-sm text-muted-foreground">
                                                        Showing {((docPage - 1) * pageSize) + 1} - {Math.min(docPage * pageSize, details.document_count)} of {details.document_count}
                                                    </p>
                                                    <div className="flex items-center gap-2">
                                                        <Button
                                                            variant="outline"
                                                            size="sm"
                                                            onClick={() => setDocPage(p => Math.max(1, p - 1))}
                                                            disabled={docPage === 1}
                                                        >
                                                            <ChevronLeft className="h-4 w-4" />
                                                            Previous
                                                        </Button>
                                                        <span className="text-sm text-muted-foreground px-2">
                                                            Page {docPage} of {Math.ceil(details.document_count / pageSize)}
                                                        </span>
                                                        <Button
                                                            variant="outline"
                                                            size="sm"
                                                            onClick={() => setDocPage(p => p + 1)}
                                                            disabled={docPage >= Math.ceil(details.document_count / pageSize)}
                                                        >
                                                            Next
                                                            <ChevronRight className="h-4 w-4" />
                                                        </Button>
                                                    </div>
                                                </div>
                                            )}
                                        </TabsContent>

                                        {/* Schedule Tab */}
                                        <TabsContent value="schedule" className="space-y-4 mt-4">
                                            {selectedSchedule ? (
                                                <div className="space-y-4">
                                                    {/* Schedule Summary */}
                                                    <div className="grid gap-3">
                                                        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                                            <span className="text-sm font-medium flex items-center gap-2">
                                                                <Timer className="h-4 w-4" />
                                                                Status
                                                            </span>
                                                            <Badge variant={selectedSchedule.enabled ? "default" : "secondary"}>
                                                                {selectedSchedule.enabled ? "Active" : "Paused"}
                                                            </Badge>
                                                        </div>
                                                        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                                            <span className="text-sm font-medium">Frequency</span>
                                                            <code className="text-xs bg-background px-2 py-1 rounded">
                                                                {selectedSchedule.cron_expression}
                                                            </code>
                                                        </div>
                                                        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                                            <span className="text-sm font-medium">Timezone</span>
                                                            <span className="text-sm">{selectedSchedule.timezone}</span>
                                                        </div>
                                                        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                                            <span className="text-sm font-medium">Next Run</span>
                                                            <span className="text-sm">
                                                                {selectedSchedule.next_run_at
                                                                    ? new Date(selectedSchedule.next_run_at).toLocaleString()
                                                                    : "—"}
                                                            </span>
                                                        </div>
                                                        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                                            <span className="text-sm font-medium">Last Run</span>
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-sm">
                                                                    {selectedSchedule.last_run_at
                                                                        ? new Date(selectedSchedule.last_run_at).toLocaleString()
                                                                        : "Never"}
                                                                </span>
                                                                {selectedSchedule.last_run_status && (
                                                                    <Badge variant={
                                                                        selectedSchedule.last_run_status === "completed" ? "default" :
                                                                            selectedSchedule.last_run_status === "error" ? "destructive" :
                                                                                "secondary"
                                                                    } className="text-xs">
                                                                        {selectedSchedule.last_run_status}
                                                                    </Badge>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                                            <span className="text-sm font-medium flex items-center gap-2">
                                                                <GitGraph className="h-4 w-4" />
                                                                Graph RAG Update
                                                            </span>
                                                            <Badge variant={selectedSchedule.update_graph_rag ? "default" : "secondary"}>
                                                                {selectedSchedule.update_graph_rag ? "Enabled" : "Disabled"}
                                                            </Badge>
                                                        </div>
                                                    </div>

                                                    {/* Edit / Delete buttons */}
                                                    <div className="flex gap-2">
                                                        <ScheduleDialog
                                                            datasourceId={details.id}
                                                            datasourceName={details.name}
                                                            existingSchedule={selectedSchedule}
                                                            graphRagAvailable={details.graph_rag_available}
                                                            onScheduleChange={() => {
                                                                getDataSourceDetails(details.id, docPage, pageSize).then((d) => {
                                                                    if (d) {
                                                                        setDetails(d);
                                                                        setSelectedSchedule(d.schedule || null);
                                                                    }
                                                                });
                                                                refresh();
                                                            }}
                                                        />
                                                    </div>
                                                </div>
                                            ) : (
                                                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                                                    <Timer className="h-8 w-8 mb-2 opacity-50" />
                                                    <p className="text-sm mb-1">No sync schedule configured</p>
                                                    <p className="text-xs mb-4">Set up automatic periodic syncing</p>
                                                    <ScheduleDialog
                                                        datasourceId={details.id}
                                                        datasourceName={details.name}
                                                        graphRagAvailable={details.graph_rag_available}
                                                        onScheduleChange={() => {
                                                            getDataSourceDetails(details.id, docPage, pageSize).then((d) => {
                                                                if (d) {
                                                                    setDetails(d);
                                                                    setSelectedSchedule(d.schedule || null);
                                                                }
                                                            });
                                                            refresh();
                                                        }}
                                                    />
                                                </div>
                                            )}
                                        </TabsContent>

                                        {/* Configuration Tab */}
                                        <TabsContent value="config" className="space-y-4 mt-4">
                                            <div className="grid gap-3">
                                                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                                    <span className="text-sm font-medium">Connector</span>
                                                    <Badge variant="outline">{details.connector_display_name}</Badge>
                                                </div>
                                                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                                                    <span className="text-sm font-medium">Connector Type</span>
                                                    <code className="text-xs bg-background px-2 py-1 rounded max-w-[300px] truncate">
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
                                                        <div className="space-y-1">
                                                            {Object.entries(details.config).map(([key, value]) => (
                                                                <div key={key} className="flex justify-between text-xs">
                                                                    <span className="text-muted-foreground">{key}</span>
                                                                    <span className="font-mono">{String(value)}</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </TabsContent>

                                        {/* Status Tab */}
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
                                </CardContent>
                            </>
                        ) : (
                            <div className="text-center py-16 text-muted-foreground">
                                Failed to load details
                            </div>
                        )}
                    </Card>
                </div>
            </div>

            {/* Delete Confirmation */}
            <AlertDialog open={!!deleteConfirmId} onOpenChange={(open) => !open && setDeleteConfirmId(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Delete Data Source?</AlertDialogTitle>
                        <AlertDialogDescription>
                            This will permanently delete this data source and all its indexed embeddings.
                            This action cannot be undone.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleDelete}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                            Delete
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    );
}
