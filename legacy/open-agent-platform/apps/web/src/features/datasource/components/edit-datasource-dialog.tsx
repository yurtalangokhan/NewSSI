"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Pencil,
    Loader2,
    Save,
    ArrowRight,
    ArrowLeft,
    RefreshCw,
} from "lucide-react";
import {
    useConnectors,
    useDataSources,
    type DataSourceDetails,
    type DataSourceUpdateInput,
    type StreamInfo,
} from "@/hooks/use-datasources";

// ============================================================================
// Sync mode options
// ============================================================================

/**
 * Sync mode combinations matching Airbyte webapp and destination-embedding
 * supported_destination_sync_modes: ["overwrite", "append"]
 *
 * Airbyte valid combos:
 *   Full refresh | Overwrite  — replaces all data each sync
 *   Full refresh | Append     — appends full snapshot to existing data
 *   Incremental  | Append     — only new/changed records appended
 */
const SYNC_MODE_COMBOS = [
    {
        value: "full_refresh|overwrite",
        syncMode: "full_refresh",
        destMode: "overwrite",
        label: "Full Refresh | Overwrite",
        description: "Replace all existing data with a complete re-sync each time",
    },
    {
        value: "full_refresh|append",
        syncMode: "full_refresh",
        destMode: "append",
        label: "Full Refresh | Append",
        description: "Append a full snapshot to existing data (data may duplicate)",
    },
    {
        value: "incremental|append",
        syncMode: "incremental",
        destMode: "append",
        label: "Incremental | Append",
        description: "Only sync new or changed records since the last sync",
    },
];

function comboKey(syncMode: string, destMode: string): string {
    return `${syncMode}|${destMode}`;
}

function parseCombo(combo: string): { syncMode: string; destMode: string } {
    const [syncMode, destMode] = combo.split("|");
    return { syncMode: syncMode || "full_refresh", destMode: destMode || "overwrite" };
}

// ============================================================================
// Edit Dialog
// ============================================================================

interface EditDataSourceDialogProps {
    details: DataSourceDetails;
    onUpdated?: (updated: DataSourceDetails) => void;
}

type EditStep = "general" | "streams" | "confirm";

export function EditDataSourceDialog({ details, onUpdated }: EditDataSourceDialogProps) {
    const [open, setOpen] = useState(false);
    const [step, setStep] = useState<EditStep>("general");
    const [saving, setSaving] = useState(false);

    // Form state
    const [name, setName] = useState(details.name);
    const [syncModeCombo, setSyncModeCombo] = useState(
        comboKey(details.sync_mode || "full_refresh", details.destination_sync_mode || "overwrite")
    );

    // Streams
    const [availableStreams, setAvailableStreams] = useState<StreamInfo[]>([]);
    const [selectedStreams, setSelectedStreams] = useState<string[]>(details.streams || []);
    const [loadingStreams, setLoadingStreams] = useState(false);

    const { getStreams } = useConnectors();
    const { updateDataSource } = useDataSources();

    // Reset form when dialog opens
    useEffect(() => {
        if (open) {
            setStep("general");
            setName(details.name);
            setSyncModeCombo(
                comboKey(details.sync_mode || "full_refresh", details.destination_sync_mode || "overwrite")
            );
            setSelectedStreams(details.streams || []);
            setAvailableStreams([]);
        }
    }, [open, details]);

    // Derive sync mode and destination mode from the combo
    const { syncMode, destMode: destSyncMode } = parseCombo(syncModeCombo);
    const currentComboLabel = SYNC_MODE_COMBOS.find(c => c.value === syncModeCombo)?.label || syncModeCombo;

    const fetchStreams = useCallback(async () => {
        if (availableStreams.length > 0) return;
        setLoadingStreams(true);
        try {
            // We can't fetch streams without the full config, so we use the
            // previously known streams from the details
            const knownStreams = details.streams || [];
            setAvailableStreams(knownStreams.map(s => ({ name: s })));
        } catch {
            // Fallback
        } finally {
            setLoadingStreams(false);
        }
    }, [availableStreams.length, details.streams]);

    const handleDiscoverStreams = async () => {
        setLoadingStreams(true);
        try {
            // Try to discover fresh streams via Airbyte — requires original config
            // Since we have masked config, we use what's available
            const streams = await getStreams(details.connector_type, {});
            if (streams.length > 0) {
                setAvailableStreams(streams);
            } else {
                // Fallback to known streams
                const knownStreams = details.streams || [];
                setAvailableStreams(knownStreams.map(s => ({ name: s })));
            }
        } catch {
            const knownStreams = details.streams || [];
            setAvailableStreams(knownStreams.map(s => ({ name: s })));
        } finally {
            setLoadingStreams(false);
        }
    };

    const toggleStream = (streamName: string) => {
        setSelectedStreams(prev =>
            prev.includes(streamName)
                ? prev.filter(s => s !== streamName)
                : [...prev, streamName]
        );
    };

    const origCombo = comboKey(details.sync_mode || "full_refresh", details.destination_sync_mode || "overwrite");

    const hasChanges = (): boolean => {
        if (name !== details.name) return true;
        if (syncModeCombo !== origCombo) return true;

        const origStreams = (details.streams || []).sort();
        const newStreams = [...selectedStreams].sort();
        if (origStreams.length !== newStreams.length) return true;
        if (origStreams.some((s, i) => s !== newStreams[i])) return true;

        return false;
    };

    const handleSave = async () => {
        setSaving(true);

        const input: DataSourceUpdateInput = {};

        if (name !== details.name) {
            input.name = name;
        }

        const comboChanged = syncModeCombo !== origCombo;
        if (comboChanged) {
            input.sync_mode = syncMode;
            input.destination_sync_mode = destSyncMode;
        }

        const origStreams = (details.streams || []).sort();
        const newStreams = [...selectedStreams].sort();
        if (origStreams.length !== newStreams.length || origStreams.some((s, i) => s !== newStreams[i])) {
            input.streams = selectedStreams;
        }

        // Always include sync_mode and destination_sync_mode when streams change
        // so that Airbyte connection is updated with the correct modes
        if (input.streams && !input.sync_mode) {
            input.sync_mode = syncMode;
        }
        if (input.streams && !input.destination_sync_mode) {
            input.destination_sync_mode = destSyncMode;
        }

        const result = await updateDataSource(details.id, input);

        setSaving(false);
        if (result) {
            setOpen(false);
            onUpdated?.(result);
        }
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" size="sm">
                    <Pencil className="h-4 w-4 mr-2" />
                    Edit
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[550px]">
                <DialogHeader>
                    <DialogTitle>Edit Data Source</DialogTitle>
                    <DialogDescription>
                        {step === "general" && "Update the name and sync settings"}
                        {step === "streams" && "Manage which streams to sync"}
                        {step === "confirm" && "Review and save your changes"}
                    </DialogDescription>
                </DialogHeader>

                {/* Step: General */}
                {step === "general" && (
                    <div className="space-y-4 py-4">
                        {/* Name */}
                        <div className="space-y-2">
                            <Label htmlFor="ds-name">Name</Label>
                            <Input
                                id="ds-name"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                placeholder="Data source name"
                            />
                        </div>

                        {/* Connector (read-only) */}
                        <div className="space-y-2">
                            <Label>Connector</Label>
                            <div className="flex items-center gap-2 p-2 rounded-md bg-muted/50 text-sm">
                                <Badge variant="outline">{details.connector_display_name}</Badge>
                                <span className="text-xs text-muted-foreground">{details.connector_type}</span>
                            </div>
                        </div>

                        {/* Sync Mode (combined) */}
                        <div className="space-y-2">
                            <Label>Sync Mode</Label>
                            <Select value={syncModeCombo} onValueChange={setSyncModeCombo}>
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {SYNC_MODE_COMBOS.map((combo) => (
                                        <SelectItem key={combo.value} value={combo.value}>
                                            {combo.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <p className="text-xs text-muted-foreground">
                                {SYNC_MODE_COMBOS.find(c => c.value === syncModeCombo)?.description}
                            </p>
                        </div>
                    </div>
                )}

                {/* Step: Streams */}
                {step === "streams" && (
                    <div className="space-y-4 py-4">
                        <div className="flex items-center justify-between">
                            <Label>Synced Streams</Label>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleDiscoverStreams}
                                disabled={loadingStreams}
                            >
                                {loadingStreams ? (
                                    <Loader2 className="h-3 w-3 animate-spin mr-1" />
                                ) : (
                                    <RefreshCw className="h-3 w-3 mr-1" />
                                )}
                                Discover Streams
                            </Button>
                        </div>

                        {loadingStreams ? (
                            <div className="flex items-center justify-center py-8">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                            </div>
                        ) : availableStreams.length > 0 ? (
                            <ScrollArea className="h-[250px] border rounded-md p-3">
                                <div className="space-y-2">
                                    {availableStreams.map((stream) => (
                                        <div
                                            key={stream.name}
                                            className="flex items-center space-x-2 p-2 rounded hover:bg-muted/50"
                                        >
                                            <Checkbox
                                                id={`stream-${stream.name}`}
                                                checked={selectedStreams.includes(stream.name)}
                                                onCheckedChange={() => toggleStream(stream.name)}
                                            />
                                            <label
                                                htmlFor={`stream-${stream.name}`}
                                                className="text-sm font-medium cursor-pointer flex-1"
                                            >
                                                {stream.name}
                                            </label>
                                            {details.streams?.includes(stream.name) && (
                                                <Badge variant="secondary" className="text-[10px]">current</Badge>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </ScrollArea>
                        ) : (
                            <div className="text-center py-8 text-muted-foreground">
                                <p className="text-sm mb-2">
                                    {details.streams && details.streams.length > 0
                                        ? `Currently syncing ${details.streams.length} stream(s)`
                                        : "No streams configured"}
                                </p>
                                <p className="text-xs">
                                    Click &quot;Discover Streams&quot; to see available streams
                                </p>
                            </div>
                        )}

                        {selectedStreams.length > 0 && (
                            <p className="text-xs text-muted-foreground">
                                {selectedStreams.length} stream(s) selected
                            </p>
                        )}
                    </div>
                )}

                {/* Step: Confirm */}
                {step === "confirm" && (
                    <div className="space-y-4 py-4">
                        <div className="space-y-3">
                            <h4 className="text-sm font-medium">Changes Summary</h4>

                            {name !== details.name && (
                                <div className="flex items-center justify-between p-2 rounded-md bg-muted/50 text-sm">
                                    <span className="text-muted-foreground">Name</span>
                                    <div className="flex items-center gap-2">
                                        <span className="line-through text-muted-foreground">{details.name}</span>
                                        <ArrowRight className="h-3 w-3" />
                                        <span className="font-medium">{name}</span>
                                    </div>
                                </div>
                            )}

                            {syncModeCombo !== origCombo && (
                                <div className="flex items-center justify-between p-2 rounded-md bg-muted/50 text-sm">
                                    <span className="text-muted-foreground">Sync Mode</span>
                                    <div className="flex items-center gap-2">
                                        <Badge variant="secondary">
                                            {SYNC_MODE_COMBOS.find(c => c.value === origCombo)?.label || origCombo}
                                        </Badge>
                                        <ArrowRight className="h-3 w-3" />
                                        <Badge variant="default">{currentComboLabel}</Badge>
                                    </div>
                                </div>
                            )}

                            {(() => {
                                const origStreams = (details.streams || []).sort();
                                const newStreams = [...selectedStreams].sort();
                                const streamsChanged = origStreams.length !== newStreams.length ||
                                    origStreams.some((s, i) => s !== newStreams[i]);

                                if (!streamsChanged) return null;

                                const added = newStreams.filter(s => !origStreams.includes(s));
                                const removed = origStreams.filter(s => !newStreams.includes(s));

                                return (
                                    <div className="p-2 rounded-md bg-muted/50 text-sm space-y-1">
                                        <span className="text-muted-foreground">Streams</span>
                                        {added.length > 0 && (
                                            <div className="flex flex-wrap gap-1">
                                                <span className="text-xs text-green-600">+ Added:</span>
                                                {added.map(s => (
                                                    <Badge key={s} variant="outline" className="text-[10px] text-green-600 border-green-600">{s}</Badge>
                                                ))}
                                            </div>
                                        )}
                                        {removed.length > 0 && (
                                            <div className="flex flex-wrap gap-1">
                                                <span className="text-xs text-red-600">- Removed:</span>
                                                {removed.map(s => (
                                                    <Badge key={s} variant="outline" className="text-[10px] text-red-600 border-red-600">{s}</Badge>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            })()}

                            {!hasChanges() && (
                                <p className="text-sm text-muted-foreground text-center py-4">
                                    No changes made
                                </p>
                            )}
                        </div>
                    </div>
                )}

                <DialogFooter className="flex justify-between">
                    <div className="flex gap-2">
                        {step !== "general" && (
                            <Button
                                variant="outline"
                                onClick={() => setStep(step === "confirm" ? "streams" : "general")}
                            >
                                <ArrowLeft className="h-4 w-4 mr-1" />
                                Back
                            </Button>
                        )}
                    </div>
                    <div className="flex gap-2">
                        {step === "general" && (
                            <Button onClick={() => {
                                fetchStreams();
                                setStep("streams");
                            }}>
                                Streams
                                <ArrowRight className="h-4 w-4 ml-1" />
                            </Button>
                        )}
                        {step === "streams" && (
                            <Button onClick={() => setStep("confirm")}>
                                Review
                                <ArrowRight className="h-4 w-4 ml-1" />
                            </Button>
                        )}
                        {step === "confirm" && (
                            <Button
                                onClick={handleSave}
                                disabled={saving || !hasChanges()}
                            >
                                {saving ? (
                                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                ) : (
                                    <Save className="h-4 w-4 mr-2" />
                                )}
                                Save Changes
                            </Button>
                        )}
                    </div>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
