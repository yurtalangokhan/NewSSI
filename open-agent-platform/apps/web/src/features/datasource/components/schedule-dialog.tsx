"use client";

import { useState, useEffect } from "react";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Clock,
    Loader2,
    Pencil,
    Plus,
    Trash2,
    Timer,
    GitGraph,
} from "lucide-react";
import {
    scheduleApi,
    type SyncSchedule,
    type SyncScheduleInput,
} from "@/hooks/use-datasources";

// ============================================================================
// Preset definitions
// ============================================================================

interface PresetOption {
    value: string;
    label: string;
    description: string;
    cron: string;
}

const PRESET_OPTIONS: PresetOption[] = [
    { value: "every_5_min", label: "Every 5 minutes", description: "High frequency", cron: "*/5 * * * *" },
    { value: "every_15_min", label: "Every 15 minutes", description: "Moderate frequency", cron: "*/15 * * * *" },
    { value: "every_30_min", label: "Every 30 minutes", description: "Standard", cron: "*/30 * * * *" },
    { value: "hourly", label: "Hourly", description: "Every hour at :00", cron: "0 * * * *" },
    { value: "every_6_hours", label: "Every 6 hours", description: "4 times a day", cron: "0 */6 * * *" },
    { value: "every_12_hours", label: "Every 12 hours", description: "Twice a day", cron: "0 */12 * * *" },
    { value: "daily", label: "Daily", description: "Every day at midnight", cron: "0 0 * * *" },
    { value: "weekly", label: "Weekly", description: "Every Monday at midnight", cron: "0 0 * * 1" },
    { value: "monthly", label: "Monthly", description: "1st of every month", cron: "0 0 1 * *" },
    { value: "custom", label: "Custom", description: "Enter cron expression", cron: "" },
];

// Days of week for the custom weekly picker
const DAYS_OF_WEEK = [
    { value: "1", label: "Mon" },
    { value: "2", label: "Tue" },
    { value: "3", label: "Wed" },
    { value: "4", label: "Thu" },
    { value: "5", label: "Fri" },
    { value: "6", label: "Sat" },
    { value: "0", label: "Sun" },
];

// ============================================================================
// Human-readable cron description
// ============================================================================

function describeCron(cron: string): string {
    const parts = cron.trim().split(/\s+/);
    if (parts.length !== 5) return cron;
    const [minute, hour, dom, month, dow] = parts;

    // Match common presets
    const preset = PRESET_OPTIONS.find((p) => p.cron === cron);
    if (preset && preset.value !== "custom") return preset.label;

    // Specific days of week
    if (dow !== "*" && dom === "*" && month === "*") {
        const dayNames: Record<string, string> = {
            "0": "Sunday", "1": "Monday", "2": "Tuesday", "3": "Wednesday",
            "4": "Thursday", "5": "Friday", "6": "Saturday",
        };
        const days = dow.split(",").map((d) => dayNames[d] || d).join(", ");
        const time = `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
        return `Every ${days} at ${time}`;
    }

    // Specific time daily
    if (dow === "*" && dom === "*" && month === "*" && !hour.includes("*") && !minute.includes("*")) {
        return `Daily at ${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
    }

    return cron;
}

// ============================================================================
// Schedule Dialog Component
// ============================================================================

interface ScheduleDialogProps {
    datasourceId: string;
    datasourceName: string;
    existingSchedule?: SyncSchedule | null;
    onScheduleChange?: () => void;
    trigger?: React.ReactNode;
    graphRagAvailable?: boolean;
}

export function ScheduleDialog({
    datasourceId,
    datasourceName,
    existingSchedule,
    onScheduleChange,
    trigger,
    graphRagAvailable,
}: ScheduleDialogProps) {
    const [open, setOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [deleting, setDeleting] = useState(false);

    // Form state
    const [preset, setPreset] = useState(existingSchedule?.preset || "daily");
    const [cronExpression, setCronExpression] = useState(
        existingSchedule?.cron_expression || "0 0 * * *"
    );
    const [enabled, setEnabled] = useState(existingSchedule?.enabled ?? true);
    const [updateGraphRag, setUpdateGraphRag] = useState(
        existingSchedule?.update_graph_rag ?? false
    );
    const [timezone, setTimezone] = useState(existingSchedule?.timezone || "UTC");

    // Custom builder state
    const [customMode, setCustomMode] = useState<"expression" | "weekly" | "time">("expression");
    const [selectedDays, setSelectedDays] = useState<string[]>(["1"]);
    const [selectedHour, setSelectedHour] = useState("0");
    const [selectedMinute, setSelectedMinute] = useState("0");

    const isEditing = !!existingSchedule;

    // Reset form when dialog opens
    useEffect(() => {
        if (open) {
            setPreset(existingSchedule?.preset || "daily");
            setCronExpression(existingSchedule?.cron_expression || "0 0 * * *");
            setEnabled(existingSchedule?.enabled ?? true);
            setUpdateGraphRag(existingSchedule?.update_graph_rag ?? false);
            setTimezone(existingSchedule?.timezone || "UTC");
        }
    }, [open, existingSchedule]);

    // Update cron expression when preset changes
    useEffect(() => {
        if (preset !== "custom") {
            const option = PRESET_OPTIONS.find((p) => p.value === preset);
            if (option) setCronExpression(option.cron);
        }
    }, [preset]);

    // Build cron from custom weekly picker
    const buildWeeklyCron = () => {
        const dow = selectedDays.sort().join(",");
        setCronExpression(`${selectedMinute} ${selectedHour} * * ${dow}`);
    };

    const buildTimeCron = () => {
        setCronExpression(`${selectedMinute} ${selectedHour} * * *`);
    };

    const handleSave = async () => {
        setSaving(true);
        const input: SyncScheduleInput = {
            cron_expression: cronExpression,
            preset,
            enabled,
            update_graph_rag: updateGraphRag,
            timezone,
        };

        let result;
        if (isEditing) {
            result = await scheduleApi.update(datasourceId, input);
        } else {
            result = await scheduleApi.create(datasourceId, input);
        }

        setSaving(false);
        if (result) {
            setOpen(false);
            onScheduleChange?.();
        }
    };

    const handleDelete = async () => {
        setDeleting(true);
        const success = await scheduleApi.remove(datasourceId);
        setDeleting(false);
        if (success) {
            setOpen(false);
            onScheduleChange?.();
        }
    };

    const toggleDay = (day: string) => {
        setSelectedDays((prev) =>
            prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]
        );
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                {trigger || (
                    <Button variant="outline" size="sm" className="gap-1.5">
                        {isEditing ? (
                            <>
                                <Pencil className="h-3 w-3" />
                                Edit Schedule
                            </>
                        ) : (
                            <>
                                <Plus className="h-3 w-3" />
                                Schedule Sync
                            </>
                        )}
                    </Button>
                )}
            </DialogTrigger>
            <DialogContent className="sm:max-w-[520px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Timer className="h-5 w-5" />
                        {isEditing ? "Edit Sync Schedule" : "Create Sync Schedule"}
                    </DialogTitle>
                    <DialogDescription>
                        Configure automatic sync for <strong>{datasourceName}</strong>
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-5 py-4">
                    {/* Preset Selector */}
                    <div className="space-y-2">
                        <Label>Frequency</Label>
                        <Select value={preset} onValueChange={setPreset}>
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {PRESET_OPTIONS.map((opt) => (
                                    <SelectItem key={opt.value} value={opt.value}>
                                        <div className="flex items-center gap-2">
                                            <span>{opt.label}</span>
                                            <span className="text-muted-foreground text-xs">
                                                {opt.description}
                                            </span>
                                        </div>
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Custom Cron Builder */}
                    {preset === "custom" && (
                        <div className="space-y-3 rounded-lg border p-3">
                            <Tabs
                                value={customMode}
                                onValueChange={(v) => setCustomMode(v as any)}
                            >
                                <TabsList className="grid w-full grid-cols-3">
                                    <TabsTrigger value="expression">Expression</TabsTrigger>
                                    <TabsTrigger value="weekly">Weekly</TabsTrigger>
                                    <TabsTrigger value="time">Daily Time</TabsTrigger>
                                </TabsList>

                                {/* Raw cron expression */}
                                <TabsContent value="expression" className="space-y-2 mt-3">
                                    <Label>Cron Expression (5-field)</Label>
                                    <Input
                                        placeholder="*/15 * * * *"
                                        value={cronExpression}
                                        onChange={(e) => setCronExpression(e.target.value)}
                                        className="font-mono"
                                    />
                                    <p className="text-xs text-muted-foreground">
                                        Format: minute hour day-of-month month day-of-week
                                    </p>
                                </TabsContent>

                                {/* Weekly day picker */}
                                <TabsContent value="weekly" className="space-y-3 mt-3">
                                    <Label>Days of Week</Label>
                                    <div className="flex gap-1.5 flex-wrap">
                                        {DAYS_OF_WEEK.map((day) => (
                                            <Button
                                                key={day.value}
                                                variant={
                                                    selectedDays.includes(day.value)
                                                        ? "default"
                                                        : "outline"
                                                }
                                                size="sm"
                                                className="w-11"
                                                onClick={() => {
                                                    toggleDay(day.value);
                                                    setTimeout(buildWeeklyCron, 0);
                                                }}
                                            >
                                                {day.label}
                                            </Button>
                                        ))}
                                    </div>
                                    <div className="flex gap-3 items-center">
                                        <div className="space-y-1">
                                            <Label className="text-xs">Hour</Label>
                                            <Select
                                                value={selectedHour}
                                                onValueChange={(v) => {
                                                    setSelectedHour(v);
                                                    setTimeout(buildWeeklyCron, 0);
                                                }}
                                            >
                                                <SelectTrigger className="w-20">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {Array.from({ length: 24 }, (_, i) => (
                                                        <SelectItem
                                                            key={i}
                                                            value={String(i)}
                                                        >
                                                            {String(i).padStart(2, "0")}
                                                        </SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-xs">Minute</Label>
                                            <Select
                                                value={selectedMinute}
                                                onValueChange={(v) => {
                                                    setSelectedMinute(v);
                                                    setTimeout(buildWeeklyCron, 0);
                                                }}
                                            >
                                                <SelectTrigger className="w-20">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map(
                                                        (m) => (
                                                            <SelectItem
                                                                key={m}
                                                                value={String(m)}
                                                            >
                                                                {String(m).padStart(2, "0")}
                                                            </SelectItem>
                                                        )
                                                    )}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    </div>
                                    <Button
                                        variant="secondary"
                                        size="sm"
                                        onClick={buildWeeklyCron}
                                    >
                                        Apply
                                    </Button>
                                </TabsContent>

                                {/* Daily at specific time */}
                                <TabsContent value="time" className="space-y-3 mt-3">
                                    <Label>Run daily at</Label>
                                    <div className="flex gap-3 items-center">
                                        <div className="space-y-1">
                                            <Label className="text-xs">Hour</Label>
                                            <Select
                                                value={selectedHour}
                                                onValueChange={(v) => {
                                                    setSelectedHour(v);
                                                    setTimeout(buildTimeCron, 0);
                                                }}
                                            >
                                                <SelectTrigger className="w-20">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {Array.from({ length: 24 }, (_, i) => (
                                                        <SelectItem
                                                            key={i}
                                                            value={String(i)}
                                                        >
                                                            {String(i).padStart(2, "0")}
                                                        </SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <span className="text-lg font-bold mt-4">:</span>
                                        <div className="space-y-1">
                                            <Label className="text-xs">Minute</Label>
                                            <Select
                                                value={selectedMinute}
                                                onValueChange={(v) => {
                                                    setSelectedMinute(v);
                                                    setTimeout(buildTimeCron, 0);
                                                }}
                                            >
                                                <SelectTrigger className="w-20">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55].map(
                                                        (m) => (
                                                            <SelectItem
                                                                key={m}
                                                                value={String(m)}
                                                            >
                                                                {String(m).padStart(2, "0")}
                                                            </SelectItem>
                                                        )
                                                    )}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    </div>
                                    <Button
                                        variant="secondary"
                                        size="sm"
                                        onClick={buildTimeCron}
                                    >
                                        Apply
                                    </Button>
                                </TabsContent>
                            </Tabs>

                            {/* Preview */}
                            <div className="flex items-center gap-2 pt-2 border-t">
                                <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                                <span className="text-xs text-muted-foreground">
                                    Cron:{" "}
                                    <code className="bg-muted px-1 rounded">
                                        {cronExpression}
                                    </code>
                                </span>
                                <span className="text-xs text-muted-foreground">
                                    → {describeCron(cronExpression)}
                                </span>
                            </div>
                        </div>
                    )}

                    {/* Cron preview for presets */}
                    {preset !== "custom" && (
                        <div className="flex items-center gap-2">
                            <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">
                                Cron:{" "}
                                <code className="bg-muted px-1.5 py-0.5 rounded text-xs">
                                    {cronExpression}
                                </code>
                            </span>
                        </div>
                    )}

                    {/* Timezone */}
                    <div className="space-y-2">
                        <Label>Timezone</Label>
                        <Select value={timezone} onValueChange={setTimezone}>
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="UTC">UTC</SelectItem>
                                <SelectItem value="Europe/Istanbul">Europe/Istanbul (UTC+3)</SelectItem>
                                <SelectItem value="Europe/London">Europe/London</SelectItem>
                                <SelectItem value="Europe/Berlin">Europe/Berlin (CET)</SelectItem>
                                <SelectItem value="America/New_York">America/New_York (EST)</SelectItem>
                                <SelectItem value="America/Los_Angeles">America/Los_Angeles (PST)</SelectItem>
                                <SelectItem value="Asia/Tokyo">Asia/Tokyo (JST)</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Graph RAG Toggle */}
                    <div className={`flex items-center justify-between rounded-lg border p-3${graphRagAvailable === false ? " opacity-60" : ""}`}>
                        <div className="space-y-0.5">
                            <Label className="flex items-center gap-2">
                                <GitGraph className="h-4 w-4" />
                                Update Graph RAG
                            </Label>
                            <p className="text-xs text-muted-foreground">
                                {graphRagAvailable === false
                                    ? "Graph RAG service is not available"
                                    : "Rebuild the knowledge graph after each successful sync"}
                            </p>
                        </div>
                        <Switch
                            checked={updateGraphRag}
                            onCheckedChange={setUpdateGraphRag}
                            disabled={graphRagAvailable === false}
                        />
                    </div>

                    {/* Enabled Toggle */}
                    <div className="flex items-center justify-between rounded-lg border p-3">
                        <div className="space-y-0.5">
                            <Label>Enabled</Label>
                            <p className="text-xs text-muted-foreground">
                                Disable to pause scheduled syncs without removing the schedule
                            </p>
                        </div>
                        <Switch checked={enabled} onCheckedChange={setEnabled} />
                    </div>
                </div>

                <DialogFooter className="gap-2 sm:gap-0">
                    {isEditing && (
                        <Button
                            variant="destructive"
                            onClick={handleDelete}
                            disabled={deleting || saving}
                            className="mr-auto"
                        >
                            {deleting ? (
                                <Loader2 className="h-4 w-4 animate-spin mr-1" />
                            ) : (
                                <Trash2 className="h-4 w-4 mr-1" />
                            )}
                            Remove
                        </Button>
                    )}
                    <Button
                        onClick={handleSave}
                        disabled={saving || !cronExpression.trim()}
                    >
                        {saving && <Loader2 className="h-4 w-4 animate-spin mr-1" />}
                        {isEditing ? "Update Schedule" : "Create Schedule"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ============================================================================
// Schedule Badge (inline indicator for the datasource list)
// ============================================================================

interface ScheduleBadgeProps {
    schedule?: { cron_expression: string; enabled: boolean } | null;
}

export function ScheduleBadge({ schedule }: ScheduleBadgeProps) {
    if (!schedule) return null;

    return (
        <Badge
            variant={schedule.enabled ? "default" : "secondary"}
            className="text-[10px] gap-1 px-1.5"
        >
            <Timer className="h-2.5 w-2.5" />
            {describeCron(schedule.cron_expression)}
        </Badge>
    );
}
