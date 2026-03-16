"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CreateDataSourceDialog } from "./create-datasource-dialog";
import { DataSourceDetailsDialog } from "./datasource-details-dialog";
import { useDataSources } from "@/hooks/use-datasources";
import {
    RefreshCw,
    Database,
    CheckCircle,
    AlertTriangle,
    Info,
    Trash2,
    Loader2
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
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

export function DataSourceList() {
    const {
        dataSources,
        loading,
        syncDataSource,
        deleteDataSource,
        getDataSourceDetails,
        getSyncStatus,
        refresh
    } = useDataSources();

    const [selectedDetailsId, setSelectedDetailsId] = useState<string | null>(null);
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
    const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());
    const [syncProgress, setSyncProgress] = useState<Record<string, { status: string; progress: number }>>({});

    // Poll sync status for active syncs
    const pollSyncStatus = useCallback(async (id: string) => {
        const status = await getSyncStatus(id);
        if (status) {
            setSyncProgress(prev => ({
                ...prev,
                [id]: { status: status.sync_status, progress: status.sync_progress }
            }));

            if (status.sync_status === "completed" || status.sync_status === "error") {
                setSyncingIds(prev => {
                    const next = new Set(prev);
                    next.delete(id);
                    return next;
                });
                refresh();
            }
        }
    }, [getSyncStatus, refresh]);

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
            setDeleteConfirmId(null);
        }
    };

    const getStatusIcon = (ds: any) => {
        const progress = syncProgress[ds.id];
        if (progress && progress.status !== "completed" && progress.status !== "error" && progress.status !== "idle") {
            return <Loader2 className="h-3 w-3 animate-spin text-blue-500" />;
        }
        if (ds.sync_status === "completed") {
            return <CheckCircle className="h-3 w-3 text-green-500" />;
        }
        if (ds.sync_status === "error") {
            return <AlertTriangle className="h-3 w-3 text-red-500" />;
        }
        return null;
    };

    return (
        <>
            <Card className="h-full">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Data Sources</CardTitle>
                    <CreateDataSourceDialog />
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
                        <div className="space-y-3">
                            {dataSources.map((ds) => {
                                const progress = syncProgress[ds.id];
                                const isSyncing = syncingIds.has(ds.id);

                                return (
                                    <div
                                        key={ds.id}
                                        className="rounded-lg border p-3 shadow-sm transition-colors hover:bg-muted/50"
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
                                                    {ds.document_count > 0 && (
                                                        <span className="text-muted-foreground">
                                                            • {ds.document_count} docs
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-1 shrink-0">
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-8 w-8"
                                                    onClick={() => setSelectedDetailsId(ds.id)}
                                                    title="View Details"
                                                >
                                                    <Info className="h-4 w-4" />
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-8 w-8"
                                                    onClick={() => handleSync(ds.id)}
                                                    disabled={isSyncing}
                                                    title="Sync Now"
                                                >
                                                    {isSyncing ? (
                                                        <Loader2 className="h-4 w-4 animate-spin" />
                                                    ) : (
                                                        <RefreshCw className="h-4 w-4" />
                                                    )}
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="h-8 w-8 text-destructive hover:text-destructive"
                                                    onClick={() => setDeleteConfirmId(ds.id)}
                                                    title="Delete"
                                                >
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </div>

                                        {/* Sync Progress */}
                                        {isSyncing && progress && (
                                            <div className="mt-3 space-y-1">
                                                <div className="flex items-center justify-between text-xs">
                                                    <span className="capitalize text-muted-foreground">
                                                        {progress.status}...
                                                    </span>
                                                    <span className="text-muted-foreground">
                                                        {progress.progress}%
                                                    </span>
                                                </div>
                                                <Progress value={progress.progress} className="h-1" />
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* Details Dialog */}
            <DataSourceDetailsDialog
                dataSourceId={selectedDetailsId}
                open={!!selectedDetailsId}
                onOpenChange={(open) => !open && setSelectedDetailsId(null)}
                getDataSourceDetails={getDataSourceDetails}
            />

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
