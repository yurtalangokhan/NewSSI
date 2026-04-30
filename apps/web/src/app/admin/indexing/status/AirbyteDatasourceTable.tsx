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
import { useTranslation } from "react-i18next";

// ── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status?: SyncStatus }) {
  const { t } = useTranslation();
  if (!status || status === "idle")
    return <Badge variant="secondary">{t("admin.indexingStatus.sync.idle")}</Badge>;
  if (status === "syncing" || status === "starting")
    return <Badge variant="in_progress">{t("admin.indexingStatus.sync.syncing")}</Badge>;
  if (status === "completed")
    return <Badge variant="success">{t("admin.indexingStatus.sync.completed")}</Badge>;
  if (status === "error")
    return <Badge variant="destructive">{t("admin.indexingStatus.sync.error")}</Badge>;
  return <Badge variant="secondary">{status}</Badge>;
}

function SyncHistoryStatusBadge({ status }: { status: SyncAttempt["status"] }) {
  const { t } = useTranslation();
  if (status === "succeeded")
    return <Badge variant="success">{t("admin.indexingStatus.sync.succeeded")}</Badge>;
  if (status === "failed")
    return <Badge variant="destructive">{t("admin.indexingStatus.sync.failed")}</Badge>;
  if (status === "cancelled")
    return <Badge variant="secondary">{t("admin.indexingStatus.sync.cancelled")}</Badge>;
  if (status === "running")
    return <Badge variant="in_progress">{t("admin.indexingStatus.sync.running")}</Badge>;
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
  { value: "every_5_min", label: "admin.indexingStatus.manage.presets.every_5_min", description: "admin.indexingStatus.manage.presets.descriptions.highFrequency", cron: "0 */5 * * * ?" },
  { value: "every_15_min", label: "admin.indexingStatus.manage.presets.every_15_min", description: "admin.indexingStatus.manage.presets.descriptions.moderateFrequency", cron: "0 */15 * * * ?" },
  { value: "every_30_min", label: "admin.indexingStatus.manage.presets.every_30_min", description: "admin.indexingStatus.manage.presets.descriptions.standard", cron: "0 */30 * * * ?" },
  { value: "hourly", label: "admin.indexingStatus.manage.presets.hourly", description: "admin.indexingStatus.manage.presets.descriptions.everyHour", cron: "0 0 * * * ?" },
  { value: "every_6_hours", label: "admin.indexingStatus.manage.presets.every_6_hours", description: "admin.indexingStatus.manage.presets.descriptions.fourTimesDay", cron: "0 0 */6 * * ?" },
  { value: "every_12_hours", label: "admin.indexingStatus.manage.presets.every_12_hours", description: "admin.indexingStatus.manage.presets.descriptions.twiceDay", cron: "0 0 */12 * * ?" },
  { value: "daily", label: "admin.indexingStatus.manage.presets.daily", description: "admin.indexingStatus.manage.presets.descriptions.everyDayMidnight", cron: "0 0 0 * * ?" },
  { value: "weekly", label: "admin.indexingStatus.manage.presets.weekly", description: "admin.indexingStatus.manage.presets.descriptions.everyMondayMidnight", cron: "0 0 0 * * 1" },
  { value: "monthly", label: "admin.indexingStatus.manage.presets.monthly", description: "admin.indexingStatus.manage.presets.descriptions.firstOfMonth", cron: "0 0 0 1 * ?" },
  { value: "custom", label: "admin.indexingStatus.manage.presets.custom", description: "admin.indexingStatus.manage.presets.descriptions.enterCron", cron: "" },
];

const DAYS_OF_WEEK = [
  { value: "1", label: "admin.indexingStatus.manage.days.mon" },
  { value: "2", label: "admin.indexingStatus.manage.days.tue" },
  { value: "3", label: "admin.indexingStatus.manage.days.wed" },
  { value: "4", label: "admin.indexingStatus.manage.days.thu" },
  { value: "5", label: "admin.indexingStatus.manage.days.fri" },
  { value: "6", label: "admin.indexingStatus.manage.days.sat" },
  { value: "0", label: "admin.indexingStatus.manage.days.sun" },
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

function describeCron(cron: string, t: any): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 6) return cron;
  const [, minute, hour, dom, month, dow] = parts as [
    string,
    string,
    string,
    string,
    string,
    string,
  ];
  const preset = SCHEDULE_PRESETS.find((p) => p.cron === cron);
  if (preset && preset.value !== "custom") return t(preset.label);
  if (dow !== "*" && dow !== "?" && dom === "*" && month === "*") {
    const days = dow
      .split(",")
      .map((d) => t(`admin.indexingStatus.manage.days.full.${d}`))
      .join(", ");
    return t("admin.indexingStatus.manage.describe.every", {
      days,
      time: `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`,
    });
  }
  if (
    (dow === "*" || dow === "?") &&
    dom === "*" &&
    month === "*" &&
    !hour.includes("*") &&
    !minute.includes("*")
  ) {
    return t("admin.indexingStatus.manage.describe.dailyAt", {
      time: `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`,
    });
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
  const { t } = useTranslation();
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
      toast.error(t("admin.indexingStatus.manage.couldNotDiscoverStreams"));
    } finally {
      setLoadingStreams(false);
    }
  }, [datasource.connector_type, t]);

  const handleSaveGeneral = useCallback(async () => {
    setSavingGeneral(true);
    try {
      await updateDatasource(datasource.id, {
        name: name !== datasource.name ? name : undefined,
        streams: streams.length > 0 ? streams : undefined,
      });
      toast.success(t("admin.indexingStatus.manage.datasourceUpdated"));
      onSaved();
      onOpenChange(false);
    } catch (e: unknown) {
      toast.error(
        e instanceof Error ? e.message : t("admin.indexingStatus.manage.failedToUpdate")
      );
    } finally {
      setSavingGeneral(false);
    }
  }, [name, datasource, streams, onSaved, onOpenChange, t]);

  const handleSaveSchedule = useCallback(async () => {
    setSavingSchedule(true);
    try {
      const input = { cron_expression: cron, preset, enabled: schedEnabled, update_graph_rag: updateGraphRag, timezone };
      if (schedule) await updateSchedule(datasource.id, input);
      else await createSchedule(datasource.id, input);
      toast.success(t("admin.indexingStatus.manage.scheduleSaved"));
      onSaved();
      onOpenChange(false);
    } catch (e: unknown) {
      toast.error(
        e instanceof Error
          ? e.message
          : t("admin.indexingStatus.manage.failedToSaveSchedule")
      );
    } finally {
      setSavingSchedule(false);
    }
  }, [cron, preset, schedEnabled, updateGraphRag, timezone, schedule, datasource.id, onSaved, onOpenChange, t]);

  const handleDeleteSchedule = useCallback(async () => {
    setDeletingSchedule(true);
    try {
      await deleteSchedule(datasource.id);
      toast.success(t("admin.indexingStatus.manage.scheduleRemoved"));
      onSaved();
      onOpenChange(false);
    } catch (e: unknown) {
      toast.error(
        e instanceof Error
          ? e.message
          : t("admin.indexingStatus.manage.failedToRemoveSchedule")
      );
    } finally {
      setDeletingSchedule(false);
    }
  }, [datasource.id, onSaved, onOpenChange, t]);

  const displayStreams = availableStreams.length > 0 ? availableStreams : datasource.streams ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SvgSettings className="h-4 w-4" />
            {t("admin.indexingStatus.manage.title", { name: datasource.name })}
          </DialogTitle>
        </DialogHeader>

        {/* Tab bar */}
        <div className="flex gap-1 border-b border-border shrink-0">
          {(["general", "schedule", "history"] as ManageTab[]).map((tabName) => (
            <button
              key={tabName}
              onClick={() => setTab(tabName)}
              className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${
                tab === tabName
                  ? "border-b-2 border-blue-500 text-text-00"
                  : "text-text-02 hover:text-text-00"
              }`}
            >
              {tabName === "schedule" ? (
                <span className="flex items-center gap-1.5">
                  <SvgClock className="h-3.5 w-3.5" />
                  {t("admin.indexingStatus.manage.tabs.schedule")}
                  {schedule && (
                    <span className="ml-1 inline-flex h-1.5 w-1.5 rounded-full bg-blue-500" />
                  )}
                </span>
              ) : tabName === "history"
                ? t("admin.indexingStatus.manage.tabs.history")
                : t("admin.indexingStatus.manage.tabs.general")}
            </button>
          ))}
        </div>

        {/* ── Tab: General ── */}
        {tab === "general" && (
          <div className="flex-1 overflow-y-auto space-y-5 py-4">
            <div className="space-y-1.5">
              <Text as="p" secondaryBody className="font-medium">
                {t("admin.indexingStatus.columns.name")}
              </Text>
              <InputTypeIn type="text" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Text as="p" secondaryBody className="font-medium">
                  {t("admin.indexingStatus.manage.streams")}
                </Text>
                <ButtonRefresh size="md" onClick={handleDiscoverStreams} disabled={loadingStreams}>
                  {loadingStreams
                    ? t("admin.indexingStatus.manage.discovering")
                    : t("admin.indexingStatus.manage.discoverStreams")}
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
                  {t("admin.indexingStatus.manage.discoverStreamsHint")}
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
              <Text as="p" secondaryBody className="font-medium">
                {t("admin.indexingStatus.manage.frequency")}
              </Text>
              <Select value={preset} onValueChange={setPreset}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SCHEDULE_PRESETS.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      <span className="flex items-center gap-2">
                        <span>{t(p.label)}</span>
                        <span className="text-xs text-text-02">
                          {t(p.description)}
                        </span>
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
                      {m === "expression"
                        ? t("admin.indexingStatus.manage.customModes.expression")
                        : m === "weekly"
                          ? t("admin.indexingStatus.manage.customModes.weekly")
                          : t("admin.indexingStatus.manage.customModes.dailyTime")}
                    </button>
                  ))}
                </div>

                {/* Expression */}
                {customMode === "expression" && (
                  <div className="space-y-2">
                    <Text as="p" secondaryBody className="text-xs font-medium">
                      {t("admin.indexingStatus.manage.cronExpression")}
                    </Text>
                    <InputTypeIn
                      type="text"
                      placeholder="0 */15 * * * ?"
                      value={cron}
                      onChange={(e) => setCron(e.target.value)}
                      className="font-mono text-sm"
                    />
                    <Text as="p" secondaryBody textLight05 className="text-xs">
                      {t("admin.indexingStatus.manage.cronFormat")}
                    </Text>
                  </div>
                )}

                {/* Weekly day picker */}
                {customMode === "weekly" && (
                  <div className="space-y-3">
                    <Text as="p" secondaryBody className="text-xs font-medium">
                      {t("admin.indexingStatus.manage.daysOfWeek")}
                    </Text>
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
                          {t(day.label)}
                        </button>
                      ))}
                    </div>
                    <div className="flex gap-3 items-end">
                      <div className="space-y-1">
                        <Text as="p" secondaryBody textLight05 className="text-xs">
                          {t("admin.indexingStatus.manage.hour")}
                        </Text>
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
                        <Text as="p" secondaryBody textLight05 className="text-xs">
                          {t("admin.indexingStatus.manage.minute")}
                        </Text>
                        <Select value={selectedMinute} onValueChange={(v) => { setSelectedMinute(v); setTimeout(buildWeeklyCron, 0); }}>
                          <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {[0,5,10,15,20,25,30,35,40,45,50,55].map((m) => (
                              <SelectItem key={m} value={String(m)}>{String(m).padStart(2, "0")}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <ButtonRefresh size="md" onClick={buildWeeklyCron}>
                        {t("admin.indexingStatus.manage.apply")}
                      </ButtonRefresh>
                    </div>
                  </div>
                )}

                {/* Daily at time */}
                {customMode === "time" && (
                  <div className="space-y-3">
                    <Text as="p" secondaryBody className="text-xs font-medium">
                      {t("admin.indexingStatus.manage.runDailyAt")}
                    </Text>
                    <div className="flex gap-3 items-end">
                      <div className="space-y-1">
                        <Text as="p" secondaryBody textLight05 className="text-xs">
                          {t("admin.indexingStatus.manage.hour")}
                        </Text>
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
                        <Text as="p" secondaryBody textLight05 className="text-xs">
                          {t("admin.indexingStatus.manage.minute")}
                        </Text>
                        <Select value={selectedMinute} onValueChange={(v) => { setSelectedMinute(v); setTimeout(buildTimeCron, 0); }}>
                          <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            {[0,5,10,15,20,25,30,35,40,45,50,55].map((m) => (
                              <SelectItem key={m} value={String(m)}>{String(m).padStart(2, "0")}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <ButtonRefresh size="md" onClick={buildTimeCron}>
                        {t("admin.indexingStatus.manage.apply")}
                      </ButtonRefresh>
                    </div>
                  </div>
                )}

                {/* Cron preview */}
                <div className="flex items-center gap-2 pt-2 border-t border-border">
                  <SvgClock className="h-3.5 w-3.5 shrink-0 text-text-02" />
                  <Text as="span" secondaryBody textLight05 className="text-xs">
                    {t("admin.indexingStatus.manage.cronLabel")}:{" "}
                    <code className="bg-background-tint-02 px-1 rounded">
                      {cron}
                    </code>
                    {cron && <> → {describeCron(cron, t)}</>}
                  </Text>
                </div>
              </div>
            )}

            {/* Cron preview for presets */}
            {preset !== "custom" && cron && (
              <div className="flex items-center gap-2">
                <SvgClock className="h-3.5 w-3.5 shrink-0 text-text-02" />
                <Text as="span" secondaryBody textLight05 className="text-sm">
                  {t("admin.indexingStatus.manage.cronLabel")}: <code className="bg-background-tint-02 px-1.5 py-0.5 rounded text-xs">{cron}</code>
                  {cron && <> → {describeCron(cron, t)}</>}
                </Text>
              </div>
            )}

            {/* Timezone */}
            <div className="space-y-1.5">
              <Text as="p" secondaryBody className="font-medium">
                {t("admin.indexingStatus.manage.timezone")}
              </Text>
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
                <Text as="p" secondaryBody className="font-medium">
                  {t("admin.indexingStatus.manage.updateGraphRag")}
                </Text>
                <Text as="p" secondaryBody textLight05 className="text-xs">
                  {t("admin.indexingStatus.manage.updateGraphRagHint")}
                </Text>
              </div>
              <label className="flex items-center cursor-pointer">
                <Checkbox checked={updateGraphRag} onCheckedChange={(v) => setUpdateGraphRag(!!v)} />
              </label>
            </div>

            {/* Enabled */}
            <div className="flex items-center justify-between rounded-lg border border-border p-3">
              <div className="space-y-0.5">
                <Text as="p" secondaryBody className="font-medium">
                  {t("admin.indexingStatus.manage.enabled")}
                </Text>
                <Text as="p" secondaryBody textLight05 className="text-xs">
                  {t("admin.indexingStatus.manage.enabledHint")}
                </Text>
              </div>
              <label className="flex items-center cursor-pointer">
                <Checkbox checked={schedEnabled} onCheckedChange={(v) => setSchedEnabled(!!v)} />
              </label>
            </div>

            {/* Next run info */}
            {schedule?.next_run_at && (
              <Text as="p" secondaryBody textLight05 className="text-xs">
                {t("admin.indexingStatus.manage.nextRun")}: {new Date(schedule.next_run_at).toLocaleString()}
              </Text>
            )}
          </div>
        )}

        {/* ── Tab: History ── */}
        {tab === "history" && (
          <div className="flex-1 overflow-y-auto py-4">
            {historyLoading && (
              <Text as="p" secondaryBody className="text-center py-8">
                {t("admin.indexingStatus.loading")}
              </Text>
            )}
            {!historyLoading && attempts.length === 0 && (
              <Text as="p" secondaryBody textLight05 className="text-center py-8">
                {t("admin.indexingStatus.manage.noSyncHistory")}
              </Text>
            )}
            {!historyLoading && attempts.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("admin.indexingStatus.manage.history.time")}</TableHead>
                    <TableHead>{t("admin.indexingStatus.columns.status")}</TableHead>
                    <TableHead>{t("admin.indexingStatus.manage.history.records")}</TableHead>
                    <TableHead>{t("admin.indexingStatus.manage.history.duration")}</TableHead>
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
                {deletingSchedule
                  ? t("admin.indexingStatus.manage.removing")
                  : t("admin.indexingStatus.manage.removeSchedule")}
              </ButtonRefresh>
            )}
          </div>
          <div className="flex gap-2">
            <ButtonRefresh onClick={() => onOpenChange(false)}>
              {tab === "history"
                ? t("admin.indexingStatus.manage.close")
                : t("admin.indexingStatus.manage.cancel")}
            </ButtonRefresh>
            {tab !== "history" && (
              <ButtonRefresh
                primary
                onClick={tab === "general" ? handleSaveGeneral : handleSaveSchedule}
                disabled={tab === "general" ? savingGeneral : (savingSchedule || !cron.trim())}
              >
                {tab === "general"
                  ? savingGeneral
                    ? t("admin.indexingStatus.manage.saving")
                    : t("admin.indexingStatus.manage.saveChanges")
                  : savingSchedule
                    ? t("admin.indexingStatus.manage.saving")
                    : schedule
                      ? t("admin.indexingStatus.manage.updateSchedule")
                      : t("admin.indexingStatus.manage.createSchedule")}
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
  const { t } = useTranslation();
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
        <div className="text-sm text-neutral-500 dark:text-neutral-300">
          {t("admin.indexingStatus.table.totalSources")}
        </div>
        <div className="text-xl font-semibold">{datasources.length}</div>
      </TableCell>
      <TableCell>
        <div className="text-sm text-neutral-500 dark:text-neutral-300">
          {t("admin.indexingStatus.table.currentlySyncing")}
        </div>
        <p className="flex text-xl mx-auto font-semibold items-center text-lg mt-1">
          {activeSyncing}/{datasources.length}
        </p>
      </TableCell>
      <TableCell>
        <div className="text-sm text-neutral-500 dark:text-neutral-300">
          {t("admin.indexingStatus.table.totalDocsIndexed")}
        </div>
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
  const { t } = useTranslation();
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
      toast.error(
        e instanceof Error
          ? e.message
          : t("admin.indexingStatus.errors.triggerSyncFailed")
      );
      setSyncing(false);
    }
  }, [datasource.id, onMutate, t]);

  const handleDelete = useCallback(async () => {
    setDeleting(true);
    try {
      await deleteDatasource(datasource.id);
      toast.success(t("admin.indexingStatus.datasourceDeleted"));
      onMutate();
    } catch (e: unknown) {
      toast.error(
        e instanceof Error
          ? e.message
          : t("admin.indexingStatus.errors.deleteFailed")
      );
    } finally {
      setDeleting(false);
      setDeleteConfirm(false);
    }
  }, [datasource.id, onMutate, t]);

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
            <SimpleTooltip tooltip={t("admin.indexingStatus.actions.syncNow")}>
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
            <SimpleTooltip tooltip={t("admin.indexingStatus.table.manageConnector")}>
              <Button
                icon={SvgSettings}
                prominence="tertiary"
                onClick={(e: React.MouseEvent) => {
                  e.stopPropagation();
                  setManageOpen(true);
                }}
              />
            </SimpleTooltip>
            <SimpleTooltip tooltip={t("modals.delete")}>
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
          entityType={t("admin.indexingStatus.table.dataSource")}
          entityName={datasource.name}
          additionalDetails={t("admin.indexingStatus.confirmDeleteDetails")}
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
  const { t } = useTranslation();
  return (
    <Table className="-mt-8 table-fixed">
      {/* invisible header row to set column widths */}
      <TableHeader>
        <TableRow className="invisible border-none">
          <TableCell className="w-[35%]">{t("admin.indexingStatus.columns.name")}</TableCell>
          <TableCell className="w-[15%]">{t("admin.indexingStatus.columns.lastSynced")}</TableCell>
          <TableCell className="w-[20%]">{t("admin.indexingStatus.columns.status")}</TableCell>
          <TableCell className="w-[15%]">{t("admin.indexingStatus.columns.totalDocs")}</TableCell>
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
                  <TableHead>{t("admin.indexingStatus.columns.name")}</TableHead>
                  <TableHead>{t("admin.indexingStatus.columns.lastSynced")}</TableHead>
                  <TableHead>{t("admin.indexingStatus.columns.status")}</TableHead>
                  <TableHead>{t("admin.indexingStatus.columns.totalDocs")}</TableHead>
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
