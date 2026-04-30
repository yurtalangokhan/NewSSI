"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Table,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
  TableHeader,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { FiChevronDown, FiChevronRight } from "react-icons/fi";
import { Button } from "@opal/components";
import { SvgSettings, SvgTrash, SvgClock } from "@opal/icons";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import Text from "@/refresh-components/texts/Text";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import ButtonRefresh from "@/refresh-components/buttons/Button";
import { ConfirmEntityModal } from "@/components/modals/ConfirmEntityModal";
import { toast } from "@/hooks/useToast";
import { timeAgo } from "@/lib/time";
import {
  AirbyteDatasource,
  SyncAttempt,
  SyncStatus,
  useDatasourceStatus,
  useDatasourceSchedule,
  useDatasourceSyncHistory,
  syncDatasource,
  deleteDatasource,
  updateDatasource,
  fetchConnectorStreams,
  createSchedule,
  updateSchedule,
  deleteSchedule,
} from "@/lib/airbyte";

// ── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status?: SyncStatus }) {
  if (!status || status === "idle") return <Badge variant="secondary">Idle</Badge>;
  if (status === "syncing" || status === "starting")
    return <Badge variant="in_progress">Syncing</Badge>;
  if (status === "completed") return <Badge variant="success">Completed</Badge>;
  if (status === "error") return <Badge variant="destructive">Error</Badge>;
  return <Badge variant="secondary">{status}</Badge>;
}

function SyncHistoryStatusBadge({ status }: { status: SyncAttempt["status"] }) {
  if (status === "succeeded") return <Badge variant="success">Succeeded</Badge>;
  if (status === "failed") return <Badge variant="destructive">Failed</Badge>;
  if (status === "cancelled") return <Badge variant="secondary">Cancelled</Badge>;
  if (status === "running") return <Badge variant="in_progress">Running</Badge>;
  if (status === "pending" || status === "incomplete")
    return <Badge variant="in_progress">{status.charAt(0).toUpperCase() + status.slice(1)}</Badge>;
  return <Badge variant="secondary">{status}</Badge>;
}

// ── Sync progress bar (polls while active) ───────────────────────────────────

function SyncProgress({
  datasource,
  onComplete,
}: {
  datasource: AirbyteDatasource;
  onComplete: () => void;
}) {
  const isActive =
    datasource.sync_status === "starting" ||
    datasource.sync_status === "syncing";
  const { status } = useDatasourceStatus(datasource.id, isActive);

  useEffect(() => {
    if (
      status &&
      (status.sync_status === "completed" || status.sync_status === "error")
    ) {
      onComplete();
    }
  }, [status, onComplete]);

  const progress = status?.sync_progress ?? datasource.sync_progress ?? 0;
  if (!isActive) return null;

  return (
    <div className="w-24">
      <div className="h-1.5 bg-neutral-200 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-500 rounded-full transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}

// ── Schedule presets ─────────────────────────────────────────────────────────

interface PresetOption {
  value: string;
  label: string;
  description: string;
  cron: string;
}

const SCHEDULE_PRESETS: PresetOption[] = [
  { value: "every_5_min",   label: "Every 5 minutes",  description: "High frequency",       cron: "0 */5 * * * ?"   },
  { value: "every_15_min",  label: "Every 15 minutes", description: "Moderate frequency",   cron: "0 */15 * * * ?"  },
  { value: "every_30_min",  label: "Every 30 minutes", description: "Standard",             cron: "0 */30 * * * ?"  },
  { value: "hourly",        label: "Hourly",           description: "Every hour at :00",    cron: "0 0 * * * ?"     },
  { value: "every_6_hours", label: "Every 6 hours",    description: "4 times a day",        cron: "0 0 */6 * * ?"   },
  { value: "every_12_hours",label: "Every 12 hours",   description: "Twice a day",          cron: "0 0 */12 * * ?"  },
  { value: "daily",         label: "Daily",            description: "Every day at midnight",cron: "0 0 0 * * ?"     },
  { value: "weekly",        label: "Weekly",           description: "Every Monday at midnight", cron: "0 0 0 * * 1" },
  { value: "monthly",       label: "Monthly",          description: "1st of every month",   cron: "0 0 0 1 * ?"     },
  { value: "custom",        label: "Custom",           description: "Enter cron expression",cron: ""               },
];

const DAYS_OF_WEEK = [
  { value: "1", label: "Mon" }, { value: "2", label: "Tue" }, { value: "3", label: "Wed" },
  { value: "4", label: "Thu" }, { value: "5", label: "Fri" }, { value: "6", label: "Sat" },
  { value: "0", label: "Sun" },
];

const TIMEZONES = [
  "UTC",
  "Europe/Istanbul",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Los_Angeles",
  "Asia/Tokyo",
];

function describeCron(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 6) return cron;
  const [, minute, hour, dom, month, dow] = parts as [string, string, string, string, string, string];
  const preset = SCHEDULE_PRESETS.find((p) => p.cron === cron);
  if (preset && preset.value !== "custom") return preset.label;
  if (dow !== "*" && dow !== "?" && dom === "*" && month === "*") {
    const dayNames: Record<string, string> = {
      "0": "Sunday","1": "Monday","2": "Tuesday","3": "Wednesday",
      "4": "Thursday","5": "Friday","6": "Saturday",
    };
    const days = dow.split(",").map((d) => dayNames[d] || d).join(", ");
    return `Every ${days} at ${hour.padStart(2,"0")}:${minute.padStart(2,"0")}`;
  }
  if ((dow === "*" || dow === "?") && dom === "*" && month === "*" && !hour.includes("*") && !minute.includes("*")) {
    return `Daily at ${hour.padStart(2,"0")}:${minute.padStart(2,"0")}`;
  }
  return cron;
}

// ── Manage Dialog (name + streams + schedule) ────────────────────────────────

type ManageTab = "general" | "schedule" | "history";
type CustomMode = "expression" | "weekly" | "time";

function ManageDialog({
  datasource,
  open,
  onOpenChange,
  onSaved,
}: {
  datasource: AirbyteDatasource;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onSaved: () => void;
}) {
  const [tab, setTab] = useState<ManageTab>("general");

  // ── general
  const [name, setName] = useState(datasource.name);
  const [streams, setStreams] = useState<string[]>(datasource.streams ?? []);
  const [availableStreams, setAvailableStreams] = useState<string[]>([]);
  const [loadingStreams, setLoadingStreams] = useState(false);
  const [savingGeneral, setSavingGeneral] = useState(false);

  // ── schedule
  const { schedule } = useDatasourceSchedule(open ? datasource.id : null);
  // ── history
  const { attempts, isLoading: historyLoading } = useDatasourceSyncHistory(datasource.id, open && tab === "history");
  const [schedEnabled, setSchedEnabled] = useState(false);
  const [preset, setPreset] = useState("daily");
  const [cron, setCron] = useState("0 0 0 * * ?");
  const [timezone, setTimezone] = useState("UTC");
  const [updateGraphRag, setUpdateGraphRag] = useState(false);
  const [customMode, setCustomMode] = useState<CustomMode>("expression");
  const [selectedDays, setSelectedDays] = useState<string[]>(["1"]);
  const [selectedHour, setSelectedHour] = useState("0");
  const [selectedMinute, setSelectedMinute] = useState("0");
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [deletingSchedule, setDeletingSchedule] = useState(false);

  useEffect(() => {
    if (open) {
      setName(datasource.name);
      setStreams(datasource.streams ?? []);
      setAvailableStreams([]);
      setTab("general");
    }
  }, [open, datasource]);

  useEffect(() => {
    if (schedule) {
      setSchedEnabled(schedule.enabled ?? false);
      setPreset(schedule.preset ?? "daily");
      setCron(schedule.cron_expression ?? "0 0 0 * * ?");
      setTimezone(schedule.timezone ?? "UTC");
      setUpdateGraphRag(schedule.update_graph_rag ?? false);
    } else {
      setSchedEnabled(false);
      setPreset("daily");
      setCron("0 0 0 * * ?");
      setTimezone("UTC");
      setUpdateGraphRag(false);
    }
  }, [schedule]);

  // Update cron when preset changes (except custom)
  useEffect(() => {
    if (preset !== "custom") {
      const found = SCHEDULE_PRESETS.find((p) => p.value === preset);
      if (found) setCron(found.cron);
    }
  }, [preset]);

  const buildWeeklyCron = useCallback(() => {
    const dow = [...selectedDays].sort().join(",");
    setCron(`0 ${selectedMinute} ${selectedHour} * * ${dow}`);
  }, [selectedDays, selectedHour, selectedMinute]);

  const buildTimeCron = useCallback(() => {
    setCron(`0 ${selectedMinute} ${selectedHour} * * ?`);
  }, [selectedHour, selectedMinute]);

  const toggleDay = (day: string) => {
    setSelectedDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]
    );
  };

  const handleDiscoverStreams = useCallback(async () => {
    setLoadingStreams(true);
    try {
      const result = await fetchConnectorStreams(datasource.connector_type, {});
      setAvailableStreams(result.map((s) => s.name));
    } catch {
      toast.error("Could not discover streams");
    } finally {
      setLoadingStreams(false);
    }
  }, [datasource.connector_type]);

  const handleSaveGeneral = useCallback(async () => {
    setSavingGeneral(true);
    try {
      await updateDatasource(datasource.id, {
        name: name !== datasource.name ? name : undefined,
        streams: streams.length > 0 ? streams : undefined,
      });
      toast.success("Data source updated");
      onSaved();
      onOpenChange(false);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to update");
    } finally {
      setSavingGeneral(false);
    }
  }, [name, datasource, streams, onSaved, onOpenChange]);

  const handleSaveSchedule = useCallback(async () => {
    setSavingSchedule(true);
    try {
      const input = { cron_expression: cron, preset, enabled: schedEnabled, update_graph_rag: updateGraphRag, timezone };
      if (schedule) await updateSchedule(datasource.id, input);
      else await createSchedule(datasource.id, input);
      toast.success("Schedule saved");
      onSaved();
      onOpenChange(false);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to save schedule");
    } finally {
      setSavingSchedule(false);
    }
  }, [cron, preset, schedEnabled, updateGraphRag, timezone, schedule, datasource.id, onSaved, onOpenChange]);

  const handleDeleteSchedule = useCallback(async () => {
    setDeletingSchedule(true);
    try {
      await deleteSchedule(datasource.id);
      toast.success("Schedule removed");
      onSaved();
      onOpenChange(false);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to remove schedule");
    } finally {
      setDeletingSchedule(false);
    }
  }, [datasource.id, onSaved, onOpenChange]);

  const displayStreams = availableStreams.length > 0 ? availableStreams : datasource.streams ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SvgSettings className="h-4 w-4" />
            Manage — {datasource.name}
          </DialogTitle>
        </DialogHeader>

        {/* Tab bar */}
        <div className="flex gap-1 border-b border-border shrink-0">
          {(["general", "schedule", "history"] as ManageTab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${
                tab === t
                  ? "border-b-2 border-blue-500 text-text-00"
                  : "text-text-02 hover:text-text-00"
              }`}
            >
              {t === "schedule" ? (
                <span className="flex items-center gap-1.5">
                  <SvgClock className="h-3.5 w-3.5" />
                  Schedule
                  {schedule && (
                    <span className="ml-1 inline-flex h-1.5 w-1.5 rounded-full bg-blue-500" />
                  )}
                </span>
              ) : t === "history" ? "Indexing History" : "General"}
            </button>
          ))}
        </div>

        {/* ── Tab: General ── */}
        {tab === "general" && (
          <div className="flex-1 overflow-y-auto space-y-5 py-4">
            <div className="space-y-1.5">
              <Text as="p" secondaryBody className="font-medium">Name</Text>
              <InputTypeIn type="text" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Text as="p" secondaryBody className="font-medium">Streams</Text>
                <ButtonRefresh size="md" onClick={handleDiscoverStreams} disabled={loadingStreams}>
                  {loadingStreams ? "Discovering…" : "Discover streams"}
                </ButtonRefresh>
              </div>
              {displayStreams.length > 0 ? (
                <div className="space-y-1 max-h-52 overflow-y-auto rounded border border-border p-3">
                  {displayStreams.map((s) => (
                    <label key={s} className="flex items-center gap-2 cursor-pointer py-0.5">
                      <Checkbox
                        checked={streams.includes(s)}
                        onCheckedChange={(checked) =>
                          setStreams((prev) => checked ? [...prev, s] : prev.filter((x) => x !== s))
                        }
                      />
                      <Text as="span" secondaryBody>{s}</Text>
                    </label>
                  ))}
                </div>
              ) : (
                <Text as="p" secondaryBody textLight05 className="text-sm">
                  Click &quot;Discover streams&quot; to load available streams.
                </Text>
              )}
            </div>
          </div>
        )}

        {/* ── Tab: Schedule ── */}
        {tab === "schedule" && (
          <div className="flex-1 overflow-y-auto space-y-5 py-4">

            {/* Frequency preset */}
            <div className="space-y-1.5">
              <Text as="p" secondaryBody className="font-medium">Frequency</Text>
              <Select value={preset} onValueChange={setPreset}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SCHEDULE_PRESETS.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      <span className="flex items-center gap-2">
                        <span>{p.label}</span>
                        <span className="text-xs text-text-02">{p.description}</span>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Custom builder */}
            {preset === "custom" && (
              <div className="rounded-lg border border-border p-3 space-y-3">
                {/* Custom sub-tabs */}
                <div className="flex gap-1 rounded-md bg-background-tint-02 p-0.5">
                  {(["expression", "weekly", "time"] as CustomMode[]).map((m) => (
                    <button
                      key={m}
                      onClick={() => setCustomMode(m)}
                      className={`flex-1 py-1 text-xs font-medium rounded transition-colors capitalize ${
                        customMode === m
                          ? "bg-background text-text-00 shadow-sm"
                          : "text-text-02 hover:text-text-00"
                      }`}
                    >
                      {m === "expression" ? "Expression" : m === "weekly" ? "Weekly" : "Daily Time"}
                    </button>
                  ))}
                </div>

                {/* Expression */}
                {customMode === "expression" && (
                  <div className="space-y-2">
                    <Text as="p" secondaryBody className="text-xs font-medium">Cron Expression (Quartz 6-field)</Text>
                    <InputTypeIn
                      type="text"
                      placeholder="0 */15 * * * ?"
                      value={cron}
                      onChange={(e) => setCron(e.target.value)}
                      className="font-mono text-sm"
                    />
                    <Text as="p" secondaryBody textLight05 className="text-xs">
                      Format: seconds minute hour day-of-month month day-of-week
                    </Text>
                  </div>
                )}

                {/* Weekly day picker */}
                {customMode === "weekly" && (
                  <div className="space-y-3">
                    <Text as="p" secondaryBody className="text-xs font-medium">Days of Week</Text>
                    <div className="flex gap-1.5 flex-wrap">
                      {DAYS_OF_WEEK.map((day) => (
                        <button
                          key={day.value}
                          onClick={() => toggleDay(day.value)}
                          className={`w-11 py-1.5 text-xs font-medium rounded border transition-colors ${
                            selectedDays.includes(day.value)
                              ? "bg-blue-500 border-blue-500 text-white"
                              : "border-border text-text-02 hover:border-blue-400 hover:text-text-00"
                          }`}
                        >
                          {day.label}
                        </button>
                      ))}
                    </div>
                    <div className="flex gap-3 items-end">
                      <div className="space-y-1">
                        <Text as="p" secondaryBody textLight05 className="text-xs">Hour</Text>
                        <Select value={selectedHour} onValueChange={(v) => { setSelectedHour(v); setTimeout(buildWeeklyCron, 0); }}>
                          <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {Array.from({ length: 24 }, (_, i) => (
                              <SelectItem key={i} value={String(i)}>{String(i).padStart(2, "0")}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <span className="pb-2 font-bold">:</span>
                      <div className="space-y-1">
                        <Text as="p" secondaryBody textLight05 className="text-xs">Minute</Text>
                        <Select value={selectedMinute} onValueChange={(v) => { setSelectedMinute(v); setTimeout(buildWeeklyCron, 0); }}>
                          <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {[0,5,10,15,20,25,30,35,40,45,50,55].map((m) => (
                              <SelectItem key={m} value={String(m)}>{String(m).padStart(2, "0")}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <ButtonRefresh size="md" onClick={buildWeeklyCron}>Apply</ButtonRefresh>
                    </div>
                  </div>
                )}

                {/* Daily at time */}
                {customMode === "time" && (
                  <div className="space-y-3">
                    <Text as="p" secondaryBody className="text-xs font-medium">Run daily at</Text>
                    <div className="flex gap-3 items-end">
                      <div className="space-y-1">
                        <Text as="p" secondaryBody textLight05 className="text-xs">Hour</Text>
                        <Select value={selectedHour} onValueChange={(v) => { setSelectedHour(v); setTimeout(buildTimeCron, 0); }}>
                          <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {Array.from({ length: 24 }, (_, i) => (
                              <SelectItem key={i} value={String(i)}>{String(i).padStart(2, "0")}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <span className="pb-2 font-bold">:</span>
                      <div className="space-y-1">
                        <Text as="p" secondaryBody textLight05 className="text-xs">Minute</Text>
                        <Select value={selectedMinute} onValueChange={(v) => { setSelectedMinute(v); setTimeout(buildTimeCron, 0); }}>
                          <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {[0,5,10,15,20,25,30,35,40,45,50,55].map((m) => (
                              <SelectItem key={m} value={String(m)}>{String(m).padStart(2, "0")}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <ButtonRefresh size="md" onClick={buildTimeCron}>Apply</ButtonRefresh>
                    </div>
                  </div>
                )}

                {/* Cron preview */}
                <div className="flex items-center gap-2 pt-2 border-t border-border">
                  <SvgClock className="h-3.5 w-3.5 shrink-0 text-text-02" />
                  <Text as="span" secondaryBody textLight05 className="text-xs">
                    Cron: <code className="bg-background-tint-02 px-1 rounded">{cron}</code>
                    {cron && <> → {describeCron(cron)}</>}
                  </Text>
                </div>
              </div>
            )}

            {/* Cron preview for presets */}
            {preset !== "custom" && cron && (
              <div className="flex items-center gap-2">
                <SvgClock className="h-3.5 w-3.5 shrink-0 text-text-02" />
                <Text as="span" secondaryBody textLight05 className="text-sm">
                  Cron: <code className="bg-background-tint-02 px-1.5 py-0.5 rounded text-xs">{cron}</code>
                </Text>
              </div>
            )}

            {/* Timezone */}
            <div className="space-y-1.5">
              <Text as="p" secondaryBody className="font-medium">Timezone</Text>
              <Select value={timezone} onValueChange={setTimezone}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TIMEZONES.map((tz) => (
                    <SelectItem key={tz} value={tz}>{tz}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Update Graph RAG */}
            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div className="space-y-0.5">
                <Text as="p" secondaryBody className="font-medium">Update Graph RAG</Text>
                <Text as="p" secondaryBody textLight05 className="text-xs">
                  Rebuild the knowledge graph after each successful sync
                </Text>
              </div>
              <label className="flex items-center cursor-pointer">
                <Checkbox checked={updateGraphRag} onCheckedChange={(v) => setUpdateGraphRag(!!v)} />
              </label>
            </div>

            {/* Enabled */}
            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div className="space-y-0.5">
                <Text as="p" secondaryBody className="font-medium">Enabled</Text>
                <Text as="p" secondaryBody textLight05 className="text-xs">
                  Disable to pause scheduled syncs without removing the schedule
                </Text>
              </div>
              <label className="flex items-center cursor-pointer">
                <Checkbox checked={schedEnabled} onCheckedChange={(v) => setSchedEnabled(!!v)} />
              </label>
            </div>

            {/* Next run info */}
            {schedule?.next_run_at && (
              <Text as="p" secondaryBody textLight05 className="text-xs">
                Next run: {new Date(schedule.next_run_at).toLocaleString()}
              </Text>
            )}
          </div>
        )}

        {/* ── Tab: History ── */}
        {tab === "history" && (
          <div className="flex-1 overflow-y-auto py-4">
            {historyLoading && (
              <Text as="p" secondaryBody className="text-center py-8">Loading…</Text>
            )}
            {!historyLoading && attempts.length === 0 && (
              <Text as="p" secondaryBody textLight05 className="text-center py-8">
                No sync history found.
              </Text>
            )}
            {!historyLoading && attempts.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Records</TableHead>
                    <TableHead>Duration</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {attempts.map((attempt) => (
                    <TableRow key={attempt.id}>
                      <TableCell className="text-xs whitespace-nowrap">
                        {attempt.created_at
                          ? new Date(attempt.created_at * 1000).toLocaleString()
                          : "-"}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <SyncHistoryStatusBadge status={attempt.status} />
                          {attempt.error_message && (
                            <SimpleTooltip
                              tooltip={attempt.error_message}
                              side="top"
                            >
                              <span className="cursor-help text-destructive text-xs leading-none">
                                ⚠
                              </span>
                            </SimpleTooltip>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm">
                        {attempt.records_synced != null ? attempt.records_synced.toLocaleString() : "-"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {attempt.duration_seconds != null
                          ? attempt.duration_seconds >= 60
                            ? `${Math.floor(attempt.duration_seconds / 60)}m ${attempt.duration_seconds % 60}s`
                            : `${attempt.duration_seconds}s`
                          : "-"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        )}

        <div className="flex items-center justify-between pt-4 border-t border-border shrink-0">
          {/* Remove schedule button (only in schedule tab, if exists) */}
          <div>
            {tab === "schedule" && schedule && (
              <ButtonRefresh
                onClick={handleDeleteSchedule}
                disabled={deletingSchedule || savingSchedule}
                className="text-red-600 border-red-300 hover:bg-red-50"
              >
                {deletingSchedule ? "Removing…" : "Remove Schedule"}
              </ButtonRefresh>
            )}
          </div>
          <div className="flex gap-2">
            <ButtonRefresh onClick={() => onOpenChange(false)}>
              {tab === "history" ? "Close" : "Cancel"}
            </ButtonRefresh>
            {tab !== "history" && (
              <ButtonRefresh
                primary
                onClick={tab === "general" ? handleSaveGeneral : handleSaveSchedule}
                disabled={tab === "general" ? savingGeneral : (savingSchedule || !cron.trim())}
              >
                {tab === "general"
                  ? savingGeneral ? "Saving…" : "Save Changes"
                  : savingSchedule ? "Saving…" : schedule ? "Update Schedule" : "Create Schedule"}
              </ButtonRefresh>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Summary row (grouped by connector type) ──────────────────────────────────

function SummaryRow({
  connectorDisplayName: displayName,
  datasources,
  isOpen,
  onToggle,
}: {
  connectorDisplayName: string;
  datasources: AirbyteDatasource[];
  isOpen: boolean;
  onToggle: () => void;
}) {
  const totalDocs = datasources.reduce(
    (sum, d) => sum + (d.document_count ?? 0),
    0
  );
  const activeSyncing = datasources.filter(
    (d) => d.sync_status === "syncing" || d.sync_status === "starting"
  ).length;

  return (
    <TableRow
      onClick={onToggle}
      className="border-border dark:hover:bg-neutral-800 dark:border-neutral-700 group hover:bg-background-settings-hover/20 bg-background-sidebar py-4 rounded-sm !border cursor-pointer"
    >
      <TableCell>
        <div className="text-xl flex items-center truncate ellipsis gap-x-2 font-semibold">
          <div className="cursor-pointer">
            {isOpen ? <FiChevronDown size={20} /> : <FiChevronRight size={20} />}
          </div>
          <span className="h-5 w-5 rounded bg-background-tint-02 flex items-center justify-center text-xs font-bold text-text-02 shrink-0">
            {displayName[0]}
          </span>
          {displayName}
        </div>
      </TableCell>
      <TableCell>
        <div className="text-sm text-neutral-500 dark:text-neutral-300">Total Sources</div>
        <div className="text-xl font-semibold">{datasources.length}</div>
      </TableCell>
      <TableCell>
        <div className="text-sm text-neutral-500 dark:text-neutral-300">Currently Syncing</div>
        <p className="flex text-xl mx-auto font-semibold items-center text-lg mt-1">
          {activeSyncing}/{datasources.length}
        </p>
      </TableCell>
      <TableCell>
        <div className="text-sm text-neutral-500 dark:text-neutral-300">Total Docs Indexed</div>
        <div className="text-xl font-semibold">{totalDocs.toLocaleString()}</div>
      </TableCell>
      <TableCell />
    </TableRow>
  );
}

// ── Individual datasource row ─────────────────────────────────────────────────

function DatasourceRow({
  datasource,
  onMutate,
}: {
  datasource: AirbyteDatasource;
  onMutate: () => void;
}) {
  const [syncing, setSyncing] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleSync = useCallback(async () => {
    setSyncing(true);
    try {
      await syncDatasource(datasource.id);
      onMutate();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to trigger sync");
      setSyncing(false);
    }
  }, [datasource.id, onMutate]);

  const handleDelete = useCallback(async () => {
    setDeleting(true);
    try {
      await deleteDatasource(datasource.id);
      toast.success("Data source deleted");
      onMutate();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to delete");
    } finally {
      setDeleting(false);
      setDeleteConfirm(false);
    }
  }, [datasource.id, onMutate]);

  const isActive =
    syncing ||
    datasource.sync_status === "starting" ||
    datasource.sync_status === "syncing";

  return (
    <>
      <TableRow className="border border-border dark:border-neutral-700 hover:bg-accent-background w-full relative">
        <TableCell>
          <p className="max-w-[200px] xl:max-w-[400px] inline-block ellipsis truncate">
            {datasource.name}
          </p>
        </TableCell>
        <TableCell>{timeAgo(datasource.last_synced_at) || "-"}</TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <StatusBadge status={datasource.sync_status} />
            {isActive && (
              <SyncProgress datasource={datasource} onComplete={onMutate} />
            )}
          </div>
        </TableCell>
        <TableCell>{datasource.document_count ?? "-"}</TableCell>
        <TableCell>
          <div className="flex items-center gap-1">
            <SimpleTooltip tooltip="Sync Now">
              <Button
                icon={undefined}
                prominence="tertiary"
                onClick={(e: React.MouseEvent) => {
                  e.stopPropagation();
                  handleSync();
                }}
                disabled={isActive}
              >
                {isActive ? "…" : "↺"}
              </Button>
            </SimpleTooltip>
            <SimpleTooltip tooltip="Manage Connector">
              <Button
                icon={SvgSettings}
                prominence="tertiary"
                onClick={(e: React.MouseEvent) => {
                  e.stopPropagation();
                  setManageOpen(true);
                }}
              />
            </SimpleTooltip>
            <SimpleTooltip tooltip="Delete">
              <Button
                icon={SvgTrash}
                prominence="tertiary"
                onClick={(e: React.MouseEvent) => {
                  e.stopPropagation();
                  setDeleteConfirm(true);
                }}
                disabled={deleting}
              />
            </SimpleTooltip>
          </div>
        </TableCell>
      </TableRow>

      <ManageDialog
        datasource={datasource}
        open={manageOpen}
        onOpenChange={setManageOpen}
        onSaved={onMutate}
      />

      {deleteConfirm && (
        <ConfirmEntityModal
          danger
          entityType="Data Source"
          entityName={datasource.name}
          additionalDetails="All indexed documents will be permanently removed."
          onClose={() => setDeleteConfirm(false)}
          onSubmit={handleDelete}
        />
      )}
    </>
  );
}

// ── Main exported table ───────────────────────────────────────────────────────

export interface AirbyteDatasourceGroup {
  connector_type: string;
  connector_display_name: string;
  datasources: AirbyteDatasource[];
}

export function AirbyteDatasourceTable({
  groups,
  toggledGroups,
  onToggle,
  onMutate,
}: {
  groups: AirbyteDatasourceGroup[];
  toggledGroups: Record<string, boolean>;
  onToggle: (key: string) => void;
  onMutate: () => void;
}) {
  return (
    <Table className="-mt-8 table-fixed">
      {/* invisible header row to set column widths */}
      <TableHeader>
        <TableRow className="invisible border-none">
          <TableCell className="w-[35%]">Name</TableCell>
          <TableCell className="w-[15%]">Last Synced</TableCell>
          <TableCell className="w-[20%]">Status</TableCell>
          <TableCell className="w-[15%]">Total Docs</TableCell>
          <TableCell className="w-[15%]" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {groups.map((group) => (
          <React.Fragment key={group.connector_type}>
            {/* spacer */}
            <TableRow className="border-none">
              <TableCell colSpan={5} className="h-4 p-0" />
            </TableRow>

            <SummaryRow
              connectorDisplayName={group.connector_display_name}
              datasources={group.datasources}
              isOpen={toggledGroups[group.connector_type] ?? false}
              onToggle={() => onToggle(group.connector_type)}
            />

            {toggledGroups[group.connector_type] && (
              <>
                <TableRow className="border border-border dark:border-neutral-700">
                  <TableHead>Name</TableHead>
                  <TableHead>Last Synced</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Total Docs</TableHead>
                  <TableHead />
                </TableRow>
                {group.datasources.map((ds) => (
                  <DatasourceRow key={ds.id} datasource={ds} onMutate={onMutate} />
                ))}
              </>
            )}
          </React.Fragment>
        ))}
      </TableBody>
    </Table>
  );
}
